"""Whole-scene scaffold proposals with deterministic constrained beam search.

Parts are observations assigned to shared surfaces. Carrier ancestry is evidence,
not proof of physical attachment. Scores are ranking heuristics, not confidence.
"""
from __future__ import annotations
import math
import re
from copy import deepcopy
from .data import json_digest


def _type(node):
    return node.get("type", node.get("typeId", ""))


def _bbox(node):
    bounds = node.get("bounds")
    if isinstance(bounds, dict):
        if bounds.get("status") == "unknown":
            return None
        bounds = bounds.get("nominal_world_xy")
    if isinstance(bounds, dict):
        bounds = [*bounds["min"], *bounds["max"]] if "min" in bounds else None
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        return None
    if any(not isinstance(v, (int,float)) or not math.isfinite(v) for v in bounds):
        return None
    return [float(v) for v in bounds]


def _union(boxes):
    boxes = [box for box in boxes if box is not None]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def observe_groups(observation):
    nodes = observation["nodes"]
    by_id = {str(n["uuid"]): n for n in nodes}
    if len(by_id) != len(nodes):
        raise ValueError("duplicate model node UUID")
    groups, excluded = {}, []
    for node in sorted(nodes, key=lambda item: str(item["uuid"])):
        if _type(node) != "Part":
            continue
        cursor, ancestors, visited, enabled = node, [], set(), True
        while cursor:
            uid = str(cursor["uuid"])
            if uid in visited:
                raise ValueError("cycle in model parent graph")
            visited.add(uid)
            enabled = enabled and cursor.get("enabled_local", cursor.get("enabled", True)) and cursor.get("enabled_effective", True)
            if cursor is not node:
                ancestors.append(cursor)
            parent = cursor.get("parent")
            if parent is not None and str(parent) not in by_id:
                raise ValueError("missing parent in model observation")
            cursor = by_id.get(str(parent)) if parent is not None else None
        if not enabled:
            excluded.append({"part": node["uuid"], "reason": "disabled_in_source"})
            continue
        carrier = next((n for n in ancestors if _type(n) in ("GridDeformer","PathDeformer")), None)
        key = str(carrier["uuid"]) if carrier else "unbound:"+str(node["uuid"])
        group = groups.setdefault(key, {"id": key, "name": carrier["name"] if carrier else node["name"],
                                       "carrier": carrier["uuid"] if carrier else None,
                                       "parts": [], "part_names": [], "boxes": [],
                                       "ancestor_names": [n["name"] for n in ancestors],
                                       "ancestor_ids": [n["uuid"] for n in ancestors]})
        group["parts"].append(node["uuid"])
        group["part_names"].append(node["name"])
        group["boxes"].append(_bbox(node))
    result = []
    for key in sorted(groups):
        group = groups[key]
        group["bounds"] = _union(group.pop("boxes"))
        group["parts"].sort(key=str)
        group["part_names"].sort()
        result.append(group)
    return result, sorted(excluded,key=lambda item:str(item["part"]))


def _matches(patterns, name):
    return any(re.search(pattern, name, re.IGNORECASE) for pattern in patterns)


def _group_matches(patterns, group):
    return any(_matches(patterns,name) for name in group.get("semantic_names",[group["name"]]))


def _part_set(group):
    return frozenset(str(part) for part in group["parts"])


def _bound_int(specification, key, default, maximum=4096):
    value = specification.get(key,default)
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{key} must be an integer in [1,{maximum}]")
    return value


def _candidate_groups(observation, seeds, specification):
    """Bounded regrouping hypotheses, deduplicated by observed Part membership.

    Native semantic subtrees and their seed remainders allow splits. Disjoint
    same-role seed groups with proximity or shared non-root ancestry allow
    unions. These are hypotheses, not inferred anatomical truth.
    """
    limit = _bound_int(specification,"max_group_candidates",256)
    merge_seed_limit = _bound_int(specification,"merge_seed_limit",16,128)
    merge_members = _bound_int(specification,"max_merge_members",8,64)
    if len(seeds) > limit:
        raise ValueError("max_group_candidates is smaller than observed seed count")
    by_node = {str(node["uuid"]):node for node in observation["nodes"]}
    part_seed = {str(part):seed["id"] for seed in seeds for part in seed["parts"]}
    seed_by_id = {seed["id"]:seed for seed in seeds}
    active = set(part_seed)
    roles = specification["primary_slots"]+specification.get("secondary_rules",[])
    paths = {}
    for uid in sorted(active):
        path, cursor = [], by_node[uid].get("parent")
        while cursor is not None:
            key = str(cursor)
            if key in path or key not in by_node:
                raise ValueError("cyclic or incomplete node ancestry")
            path.append(key)
            cursor = by_node[key].get("parent")
        paths[uid] = path

    def make_group(parts, gid, name, kind, semantic_names=None, evidence=None):
        parts = sorted(set(parts),key=str)
        common = set(paths[parts[0]]) if parts else set()
        for uid in parts[1:]: common &= set(paths[uid])
        common = sorted(common)
        seed_ids = sorted({part_seed[uid] for uid in parts})
        return {"id":gid,"name":name,
                "carrier":seed_by_id[seed_ids[0]]["carrier"] if len(seed_ids)==1 else None,
                "parts":[by_node[uid]["uuid"] for uid in parts],
                "part_names":sorted(by_node[uid].get("name","") for uid in parts),
                "ancestor_ids":[by_node[uid]["uuid"] for uid in common],
                "ancestor_names":[by_node[uid].get("name","") for uid in common],
                "bounds":_union([_bbox(by_node[uid]) for uid in parts]),
                "seed_ids":seed_ids,"candidate_kind":kind,
                "semantic_names":sorted(set(semantic_names or [name])),
                "proposal_evidence":[] if evidence is None else [evidence]}

    groups, by_parts, dropped = [], {}, 0
    def add(group):
        nonlocal dropped
        key = _part_set(group)
        if not key: return None
        if key in by_parts:
            existing = by_parts[key]
            existing["semantic_names"] = sorted(set(existing["semantic_names"]) | set(group["semantic_names"]))
            proofs = existing["proposal_evidence"]+group["proposal_evidence"]
            unique = {json_digest(proof):proof for proof in proofs}
            existing["proposal_evidence"] = [unique[key] for key in sorted(unique)]
            return existing
        if len(groups) >= limit:
            dropped += 1
            return None
        groups.append(group);by_parts[key]=group
        return group

    for seed in seeds:
        add(make_group(_part_set(seed),seed["id"],seed["name"],"observed_carrier_seed",
                       evidence={"kind":"observed_carrier","carrier":seed["carrier"]}))
    native = []
    for uid,node in sorted(by_node.items()):
        hits = sorted(role["id"] for role in roles if _matches(role.get("name_patterns",[]),node.get("name","")))
        if not hits: continue
        members = {part for part in active if part==uid or uid in paths[part]}
        if not members: continue
        # A material Part or in-carrier semantic node must not absorb all new
        # child carriers (e.g. neck artwork also parenting the complete head).
        owner = part_seed.get(uid)
        if owner is None:
            cursor = node.get("parent")
            while cursor is not None:
                key = str(cursor)
                if key in seed_by_id:
                    owner = key;break
                cursor = by_node[key].get("parent")
        if owner is not None:
            members = {part for part in members if part_seed[part]==owner}
        if not members: continue
        group = make_group(members,"native:"+uid,node.get("name",""),"semantic_native_subtree",
                           evidence={"kind":"semantic_native_subtree","node":node["uuid"],
                                     "role_pattern_hits":hits,"same_carrier_restriction":owner})
        native.append(group)
    for group in native: add(group)
    # One cut per meaningful proper subgroup plus the union of cuts. This is
    # bounded and does not enumerate all 2^N subsets of a carrier.
    for seed in seeds:
        full = _part_set(seed)
        cuts = sorted({_part_set(group) for group in native if _part_set(group) < full},
                      key=lambda parts:tuple(sorted(parts)))
        if cuts:
            cuts += [frozenset().union(*cuts)]
        for cut in cuts:
            remainder = full-cut
            if not remainder: continue
            identity = json_digest(sorted(remainder))[:12]
            add(make_group(remainder,"split:"+seed["id"]+":"+identity,seed["name"],"seed_remainder",
                           evidence={"kind":"semantic_subtree_removed","seed":seed["id"],
                                     "removed_parts":sorted(cut)}))

    gap_limit = specification.get("merge_max_gap_ratio",.2)
    if not isinstance(gap_limit,(int,float)) or not math.isfinite(gap_limit) or gap_limit < 0:
        raise ValueError("merge_max_gap_ratio must be finite and nonnegative")
    # Seeds may have gained semantic aliases through exact-set deduplication.
    enriched_seeds = [by_parts[_part_set(seed)] for seed in seeds]
    merge_proposals = []
    for role in specification["primary_slots"]:
        eligible = [g for g in enriched_seeds if _group_matches(role.get("name_patterns",[]),g)]
        eligible = sorted(eligible,key=lambda g:g["id"])[:merge_seed_limit]
        adjacency = {g["id"]:set() for g in eligible}
        proofs = {}
        for i,left in enumerate(eligible):
            for right in eligible[i+1:]:
                if _part_set(left) & _part_set(right): continue
                common = set(left["ancestor_ids"]) & set(right["ancestor_ids"])
                a,b = left["bounds"],right["bounds"]
                # Unrelated appendages must not enlarge the permissible merge
                # distance. This scale belongs only to the two compared groups.
                span = max(a[2]-a[0],a[3]-a[1],b[2]-b[0],b[3]-b[1],1e-12) if a and b else None
                gap = None if a is None or b is None else math.hypot(
                    max(a[0]-b[2],b[0]-a[2],0),max(a[1]-b[3],b[1]-a[3],0))/span
                if not ((gap is not None and gap <= gap_limit) or len(common)>1): continue
                adjacency[left["id"]].add(right["id"]);adjacency[right["id"]].add(left["id"])
                proof = {"kind":"same_role_seed_union","role_pattern_hit":role["id"],
                         "seed_ids":[left["id"],right["id"]],"normalized_gap":gap,
                         "gap_scale":"pair_local_extent","gap_scale_value":span,
                         "shared_ancestors":len(common)}
                proofs[frozenset((left["id"],right["id"]))] = proof
                merge_proposals.append(([left,right],proof))
        seen = set();by_eligible = {g["id"]:g for g in eligible}
        for start in sorted(adjacency):
            if start in seen: continue
            stack,component=[start],[]
            while stack:
                gid=stack.pop()
                if gid in seen: continue
                seen.add(gid);component.append(gid)
                stack.extend(sorted(adjacency[gid]-seen,reverse=True))
            if 2 < len(component) <= merge_members:
                merge_proposals.append(([by_eligible[gid] for gid in sorted(component)],
                    {"kind":"connected_same_role_seed_union","role_pattern_hit":role["id"],
                     "seed_ids":sorted(component)}))
    for components,proof in merge_proposals:
        members = frozenset().union(*(_part_set(group) for group in components))
        names = sorted({name for group in components for name in group["semantic_names"]})
        add(make_group(members,"merge:"+json_digest(sorted(members))[:16]," + ".join(g["name"] for g in components),
                       "same_role_seed_union",names,proof))
    return sorted(groups,key=lambda group:group["id"]), {
        "candidate_limit":limit,"candidate_count":len(groups),"dropped_at_limit":dropped,
        "merge_seed_limit_per_role":merge_seed_limit,"max_merge_members":merge_members,
        "part_membership_deduplicated":True,"complete_structure_search":False}, make_group


def _features(group, bounds):
    box = group["bounds"]
    if box is None or bounds is None:
        return None
    w,h = max(bounds[2]-bounds[0],1e-12), max(bounds[3]-bounds[1],1e-12)
    return [(box[0]+box[2]-2*bounds[0])/(2*w), (box[1]+box[3]-2*bounds[1])/(2*h),
            (box[2]-box[0])/w, (box[3]-box[1])/h]


def _cost(slot, group, whole, all_slots):
    name_hit = _group_matches(slot.get("name_patterns", []), group)
    other_hit = any(s["id"] != slot["id"] and
                    _group_matches(s.get("name_patterns", []), group) for s in all_slots)
    cost = 0.0 if name_hit else 2.5
    if other_hit and not name_hit:
        cost += 2.0
    feature = _features(group, whole)
    if feature is None:
        cost += 1.0
    else:
        position, size = slot.get("position",[.5,.5]), slot.get("size",[.3,.3])
        cost += 2*sum((feature[i]-position[i])**2 for i in (0,1))
        cost += .5*sum((feature[i+2]-size[i])**2 for i in (0,1))
    return cost, {"semantic_name_match": name_hit, "normalized_bounds": feature,
                  "candidate_kind":group.get("candidate_kind","observed_carrier_seed"),
                  "proposal_evidence":group.get("proposal_evidence",[]),
                  "nominal_geometry_only": True}


def _relation_cost(assignment, by_group, whole, relations):
    penalty = 0.0
    for relation in relations:
        a, b = assignment.get(relation["a"]), assignment.get(relation["b"])
        if a is None or b is None:
            continue
        fa, fb = _features(by_group[a],whole), _features(by_group[b],whole)
        if fa is None or fb is None:
            continue
        kind = relation["kind"]
        axis = 1 if kind in ("above","below") else 0
        delta = fa[axis]-fb[axis]
        if kind in ("below","right_of"):
            delta = -delta
        if kind not in ("above","below","left_of","right_of"):
            raise ValueError(f"unknown structure relation {kind}")
        penalty += relation.get("weight",4.0)*max(0.0,delta+relation.get("margin",0.0))**2
    return penalty


def _rank_hosts(group, host_slots, selected, by_group, whole, probe_uv=(.5,0)):
    ranked = []
    span = max(whole[2]-whole[0],whole[3]-whole[1],1e-12) if whole else 1.0
    box = group["bounds"]
    for slot in host_slots:
        gid = selected.get(slot)
        if gid is None:
            continue
        host = by_group[gid]
        hbox = host["bounds"]
        score, geometry_used = 1.0, False
        if box is not None and hbox is not None:
            p = [box[i]+probe_uv[i]*(box[i+2]-box[i]) for i in (0,1)]
            outside = [max(hbox[i]-p[i],0,p[i]-hbox[i+2])/span for i in (0,1)]
            center = [(p[i]-(hbox[i]+hbox[i+2])/2)/span for i in (0,1)]
            score = 8*sum(x*x for x in outside)+.5*sum(x*x for x in center)
            geometry_used = True
        # Shared non-root ancestry is supporting evidence only.
        common = set(group["ancestor_ids"]) & set(host["ancestor_ids"])
        score -= .02*max(0,len(common)-1)
        ranked.append({"surface":"surface:"+gid,"slot":slot,"score":score,
                       "geometry_used":geometry_used,"shared_ancestors":len(common)})
    return sorted(ranked,key=lambda row:(row["score"],row["surface"]))


def _normalization_policy(specification, slots):
    value = specification.get("normalization",{})
    if not isinstance(value,dict):
        raise ValueError("normalization must be an object")
    mode = value.get("coordinate_system","enabled_observation_bounds")
    if mode not in ("enabled_observation_bounds","primary_scaffold_hypotheses"):
        raise ValueError("unknown normalization coordinate_system")
    required = value.get("required_slots",[slot["id"] for slot in slots])
    known = {slot["id"] for slot in slots}
    if (not isinstance(required,list) or not required or
            any(not isinstance(sid,str) for sid in required) or
            len(set(required)) != len(required) or set(required)-known):
        raise ValueError("normalization required_slots must name distinct primary slots")
    return {"coordinate_system":mode,"required_slots":required,
            "hypothesis_limit":_bound_int(value,"hypothesis_limit",3,16),
            "iterations":_bound_int(value,"iterations",2,4)}


def _assignment_frame(assignment, by_group, whole, policy):
    baseline = {"id":"enabled:"+json_digest(whole)[:16],
                "kind":"enabled_observation_bounds","bounds":whole,
                "anatomical_bounds_verified":False,"fallback":False}
    if policy["coordinate_system"] == "enabled_observation_bounds":
        return baseline
    missing, boxes, owners = [], [], {}
    for sid in policy["required_slots"]:
        gid = assignment.get(sid)
        box = None if gid is None else by_group[gid]["bounds"]
        if gid is None:
            missing.append({"slot":sid,"reason":"unassigned"})
        elif box is None or box[2] <= box[0] or box[3] <= box[1]:
            missing.append({"slot":sid,"reason":"missing_or_degenerate_geometry"})
        else:
            boxes.append(box);owners[sid]=gid
    if missing:
        return {**baseline,"fallback":True,"fallback_reasons":missing}
    bounds = _union(boxes)
    return {"id":"scaffold:"+json_digest({"owners":owners,"bounds":bounds})[:16],
            "kind":"primary_scaffold_candidate","bounds":bounds,
            "scaffold_assignment":owners,"anatomical_bounds_verified":False,
            "fallback":False,"evidence":"nominal_bounds_of_assigned_scaffold_groups"}


def _shape_proposal_cost(slot, group):
    """A weak frame-independent reserve, never used as an acceptance score.

    Normalized template aspect is only a proposal cue because scene aspect is
    unknown. Reserving candidates prevents all branches depending exclusively
    on an appendage-distorted whole-scene positional ranking.
    """
    box,size=group["bounds"],slot.get("size",[.3,.3])
    if box is None or box[2] <= box[0] or box[3] <= box[1] or min(size) <= 0:
        return math.inf
    return abs(math.log((box[2]-box[0])/(box[3]-box[1]))-math.log(size[0]/size[1]))


def _search_assignments(groups, slots, by_group, bounds, specification, fixed, shape_reserve=False):
    costs,candidates={},{}
    for slot in slots:
        sid=slot["id"]
        costs[sid]={group["id"]:_cost(slot,group,bounds,slots)[0] for group in groups}
        ranked=sorted(costs[sid],key=lambda gid:(costs[sid][gid],gid))
        shortlist=ranked[:specification.get("candidate_width",6)]
        if shape_reserve:
            reserve=sorted(groups,key=lambda group:(_shape_proposal_cost(slot,group),group["id"]))[:2]
            shortlist=list(dict.fromkeys(shortlist+[group["id"] for group in reserve]))
        candidates[sid]=[fixed[sid]] if sid in fixed else shortlist+[None]
    beam=[(0.0,{})]
    for slot in slots:
        sid=slot["id"];expanded=[]
        for _,partial in beam:
            occupied=set().union(*(_part_set(by_group[value]) for value in partial.values() if value is not None))
            for gid in candidates[sid]:
                if gid is not None and occupied & _part_set(by_group[gid]):
                    continue
                assignment={**partial,sid:gid}
                score=sum(costs[key][value] if value is not None else specification.get("missing_slot_cost",5.0)
                          for key,value in assignment.items())
                score+=_relation_cost(assignment,by_group,bounds,specification.get("relations",[]))
                expanded.append((score,assignment))
        expanded.sort(key=lambda row:(row[0],json_digest(row[1])))
        beam=expanded[:specification.get("beam_width",128)]
    return beam


def _scored_hypotheses(groups, slots, by_group, whole, specification, fixed, policy):
    if policy["coordinate_system"] == "enabled_observation_bounds":
        beam=_search_assignments(groups,slots,by_group,whole,specification,fixed)
        frame=_assignment_frame({},by_group,whole,policy)
        return [(score,assignment,frame) for score,assignment in beam], {
            **policy,"observed_bounds":whole,"evaluated_frames":[frame],
            "complete_frame_search":False,"shape_reserve_per_slot":0}
    assignments={}
    evaluated={}
    baseline={"id":"enabled:"+json_digest(whole)[:16],"kind":"enabled_observation_bounds",
              "bounds":whole,"anatomical_bounds_verified":False,"bootstrap_only":True}
    pending=[baseline]
    ranked=[]
    def rank_assignments():
        rows=[]
        for assignment in assignments.values():
            frame=_assignment_frame(assignment,by_group,whole,policy)
            score=sum(_cost(slot,by_group[assignment[slot["id"]]],frame["bounds"],slots)[0]
                      if assignment[slot["id"]] is not None else specification.get("missing_slot_cost",5.0)
                      for slot in slots)
            score+=_relation_cost(assignment,by_group,frame["bounds"],specification.get("relations",[]))
            rows.append((score,assignment,frame))
        return sorted(rows,key=lambda row:(row[0],json_digest(row[1])))
    # Each assignment is scored in its OWN envelope. A frame is a search
    # hypothesis, not a claim that its selected observations are anatomy.
    for iteration in range(policy["iterations"]+1):
        for frame in pending:
            # Different semantic ownership can yield the same numeric frame.
            # Keep those assignment branches, but do not spend search budget
            # repeatedly evaluating identical normalized coordinates.
            evaluated[json_digest(frame["bounds"])]=frame
            beam=_search_assignments(groups,slots,by_group,frame["bounds"],specification,fixed,True)
            for _,assignment in beam:
                assignments[json_digest(assignment)]=assignment
        ranked=rank_assignments()
        # A candidate excluded by a distorted bootstrap shortlist must still
        # be able to enter. Try one-slot exchanges from a bounded set of the
        # best distinct numeric frames, using every bounded group candidate.
        refinement_seeds=[];seed_frames=set()
        for _,assignment,frame in ranked:
            key=json_digest(frame["bounds"])
            if key in seed_frames: continue
            refinement_seeds.append(assignment);seed_frames.add(key)
            if len(refinement_seeds) >= policy["hypothesis_limit"]: break
        before=len(assignments)
        for assignment in refinement_seeds:
            for slot in slots:
                sid=slot["id"]
                if sid in fixed: continue
                occupied=set().union(*(_part_set(by_group[gid]) for key,gid in assignment.items()
                                      if key != sid and gid is not None))
                for gid in [group["id"] for group in groups]+[None]:
                    if gid is not None and occupied & _part_set(by_group[gid]): continue
                    proposal={**assignment,sid:gid}
                    assignments[json_digest(proposal)]=proposal
        ranked=rank_assignments()
        pending=[];seen=set(evaluated)
        for _,_,frame in ranked:
            key=json_digest(frame["bounds"])
            if frame["kind"] != "primary_scaffold_candidate" or key in seen:
                continue
            pending.append(frame);seen.add(key)
            if len(pending) >= policy["hypothesis_limit"]:
                break
        if (not pending and len(assignments)==before) or iteration == policy["iterations"]:
            break
    return ranked, {**policy,"observed_bounds":whole,
                    "evaluated_frames":list(evaluated.values()),
                    "complete_frame_search":False,"shape_reserve_per_slot":2,
                    "local_refinement":{"kind":"one_slot_exchange","seed_limit":policy["hypothesis_limit"],
                                        "rounds_completed":iteration+1,"complete":False},
                    "assignment_candidates_scored":len(assignments)}


def infer_structure(observation, specification, hints=None):
    hints = hints or {}
    seeds, excluded = observe_groups(observation)
    slots = specification["primary_slots"]
    if len({s["id"] for s in slots}) != len(slots):
        raise ValueError("duplicate structural slot")
    groups, candidate_audit, make_group = _candidate_groups(observation,seeds,specification)
    by_group = {g["id"]: g for g in groups}
    by_slot = {s["id"]: s for s in slots}
    fixed = {key: str(value) for key,value in hints.get("primary_assignments",{}).items()}
    if set(fixed)-set(by_slot) or set(fixed.values())-set(by_group):
        raise ValueError("structural hint references unknown slot or group")
    fixed_parts = set()
    for gid in fixed.values():
        members = _part_set(by_group[gid])
        if fixed_parts & members:
            raise ValueError("structural hints assign overlapping Parts to multiple slots")
        fixed_parts.update(members)
    whole = _union([g["bounds"] for g in seeds])
    policy = _normalization_policy(specification,slots)
    beam, normalization = _scored_hypotheses(groups,slots,by_group,whole,specification,fixed,policy)
    if not beam:
        raise ValueError("no feasible structural assignment")
    top = beam[:3]
    selected_index = hints.get("hypothesis_index",0)
    if not isinstance(selected_index,int) or not 0 <= selected_index < len(top):
        raise ValueError("invalid hypothesis_index")
    score, selected, selected_frame = top[selected_index]
    normalization["selected_frame"] = selected_frame
    normalization["frame_hypotheses"] = [{"score":s,"frame":f,"assignment":a} for s,a,f in top]
    selected_bounds = selected_frame["bounds"]
    margin = top[1][0]-top[0][0] if len(top)>1 else None
    questions = []
    if len(top)>1 and margin < specification.get("ambiguity_margin",.3):
        for sid in by_slot:
            alternatives = sorted({a.get(sid) for _,a,_ in top},key=lambda v: str(v))
            if len(alternatives)>1 and sid not in fixed:
                questions.append({"kind":"structural_assignment","slot":sid,"candidate_groups":alternatives})
        if len({frame["id"] for _,_,frame in top}) > 1:
            questions.append({"kind":"normalization_frame",
                              "candidate_frame_ids":sorted({frame["id"] for _,_,frame in top})})
    if selected_frame.get("fallback"):
        questions.append({"kind":"scaffold_normalization_fallback",
                          "reasons":selected_frame["fallback_reasons"]})
    for sid,gid in selected.items():
        if gid is None:
            questions.append({"kind":"unobserved_structural_slot","slot":sid})
    surfaces, assignments = [], []
    primary_by_group = {gid:sid for sid,gid in selected.items() if gid is not None}
    claimed = set().union(*(_part_set(by_group[gid]) for gid in primary_by_group))
    realized = [by_group[gid] for gid in primary_by_group]
    # Unselected observations remain covered exactly once. They retain the
    # observed seed unless a selected split/union has consumed part of it.
    for seed in seeds:
        remaining = _part_set(seed)-claimed
        if not remaining: continue
        if remaining == _part_set(seed):
            realized.append(by_group[seed["id"]])
        else:
            gid = "remaining:"+seed["id"]+":"+json_digest(sorted(remaining))[:12]
            realized.append(make_group(remaining,gid,seed["name"],"unclaimed_seed_remainder",
                evidence={"kind":"remaining_observed_membership","seed":seed["id"]}))
    realized = sorted(realized,key=lambda group:group["id"])
    for group in realized:
        gid = group["id"]
        if gid in primary_by_group:
            sid = primary_by_group[gid]
            surfaces.append({"id":"surface:"+gid,"group":gid,"structural_role":sid,
                             "template_id":by_slot[sid]["template_id"],"host_candidates":[],
                             "relation":"primary_scaffold","part_count":len(group["parts"]),
                             "evidence":{**_cost(by_slot[sid],group,selected_bounds,slots)[1],
                                         "normalization_frame_id":selected_frame["id"]}})
        else:
            matches = [r for r in specification.get("secondary_rules",[])
                       if _group_matches(r.get("name_patterns",[]),group)]
            if len(matches) == 1:
                rule = matches[0]
                host_ranking = _rank_hosts(group,rule.get("host_slots",[]),selected,by_group,selected_bounds,
                                           rule.get("attachment_probe_uv",[.5,0]))
                hosts = [entry["surface"] for entry in host_ranking]
                host_choice = hosts[0] if len(hosts)==1 or (len(hosts)>1 and
                    host_ranking[1]["score"]-host_ranking[0]["score"] >= specification.get("host_ambiguity_margin",.01)) else None
                surfaces.append({"id":"surface:"+gid,"group":gid,"structural_role":rule["id"],
                                 "template_id":rule["template_id"],"host_candidates":hosts,
                                 "host_ranking":host_ranking,"proposed_host":host_choice,
                                 "fit_policy":rule.get("fit_policy","unreviewed_candidate"),
                                 "material_status":rule.get("material_status","unknown"),
                                 "alternative_templates":rule.get("alternative_templates",[]),
                                 "parameter_overrides":rule.get("parameter_overrides",{}),
                                 "relation":rule["kind"],"part_count":len(group["parts"]),
                                 "attachment_required":bool(rule.get("host_slots")) or bool(rule.get("host_required")),
                                 "evidence":{"semantic_name_match":True,"attachment_confirmed":False}})
                if surfaces[-1]["attachment_required"] and host_choice is None:
                    questions.append({"kind":"attachment_host" if hosts else "attachment_host_missing",
                                      "group":gid,"candidates":hosts})
            else:
                surfaces.append({"id":"surface:"+gid,"group":gid,"structural_role":None,
                                 "template_id":None,"host_candidates":[],"relation":"unresolved",
                                 "part_count":len(group["parts"])})
                questions.append({"kind":"surface_topology","group":gid,
                                  "candidates":[r["id"] for r in matches]})
        assignments.extend({"part":part,"surface":"surface:"+gid,
                            "basis":group.get("candidate_kind","observed_carrier_seed"),
                            "material_attachment_confirmed":False}
                           for part in group["parts"])
    observed_parts = set().union(*(_part_set(seed) for seed in seeds))
    assigned_parts = [str(row["part"]) for row in assignments]
    if len(assigned_parts) != len(set(assigned_parts)) or set(assigned_parts) != observed_parts:
        raise ValueError("structural assignment must own every active observed Part exactly once")
    connections = [{"surface":s["id"],"host":s.get("proposed_host"),"kind":s["relation"],
                    "shared_geometry":s["relation"] in ("shared_offset","shared_surface","fitted_layer"),
                    "confirmed":False,"resolved_candidate":s.get("proposed_host") is not None}
                    for s in surfaces if s.get("host_candidates") or s.get("attachment_required")]
    return {"schema_version":"rig-structure/1","status":"structural_proposal",
            "source":observation["source"],"specification_id":specification["id"],
            "specification_sha256":json_digest(specification),"groups":realized,
            "observation_seeds":seeds,"group_candidates":groups,"candidate_generation":candidate_audit,
            "hypotheses":[{"score":s,"assignment":a,"normalization_frame_id":f["id"]} for s,a,f in top],
            "selected_hypothesis":selected_index,"score_margin":margin,
            "normalization":normalization,
            "surfaces":surfaces,"connections":connections,"part_assignments":assignments,"excluded_parts":excluded,
            "questions":questions,
            "coverage":{"active_parts":len(assignments),"shared_surfaces":len(surfaces),
                        "unique_part_ownership":True,
                        "unresolved_surfaces":sum(s["template_id"] is None or
                            (bool(s.get("attachment_required")) and s.get("proposed_host") is None) for s in surfaces),
                        "unresolved_attachments":sum(bool(s.get("attachment_required")) and
                            s.get("proposed_host") is None for s in surfaces)},
            "limitations":["Bounded beam search is not a proof of the globally optimal structure.",
                           "Bounded native-subtree splits and same-role seed unions do not recover arbitrary anatomy or topology.",
                           "Native hierarchy and labels are evidence, not physical attachment truth.",
                           "Scaffold envelopes are bounded-search candidates; neither anatomy nor true body boundaries are certified.",
                           "Bounds are nominal TRS observations; live deformation is not evaluated.",
                           "Depth, material, unseen topology and intended motion remain prior-dependent."],
            "live_model_modified":False}
