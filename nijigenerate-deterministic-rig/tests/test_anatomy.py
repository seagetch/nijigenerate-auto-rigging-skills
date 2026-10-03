import copy
import json
import math
from pathlib import Path
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from riglib.anatomy import solve_scaffold,depth_field,regular_mesh


def evidence():
    # Independent normalized synthetic humanoid, with different proportions.
    points={'head_top':[0,0],'head_root':[0,2],'neck_base':[0,2.4],'chest':[0,3],'waist':[0,4.2],'pelvis':[0,5]}
    for side,sign in [('L',-1),('R',1)]:
        for name,x,y in [('shoulder',1,2.5),('elbow',1.6,3.5),('wrist',2,4.6),('hand_tip',2.2,5),('hip',.5,5),('knee',.55,6.8),('ankle',.55,8.5),('foot_tip',.7,9)]:
            points[f'{name}.{side}']=[sign*x,y]
    return {'source_to_model':[[1,0,0],[0,1,0],[0,0,1]],
            'landmarks':{k:{'xy':v,'provenance':'visual_estimate'} for k,v in points.items()},
            'volumes':{'head':{'center':[0,1],'radii':[.8,1]},'torso':{'center':[0,3.6],'radii':[1,1.3]}}}


class AnatomyTests(unittest.TestCase):
    def setUp(self):
        self.prior=json.loads((ROOT/'structures'/'humanoid-prior.json').read_text())

    def test_shared_joint_endpoints_and_nonzero_bones(self):
        out=solve_scaffold(evidence(),self.prior)
        bones={b['id']:b for b in out['bones']}
        self.assertEqual(bones['Spine']['tail'],bones['Chest']['head'])
        self.assertEqual(bones['Forearm.L']['tail'],bones['Hand.L']['head'])
        self.assertTrue(all(np.linalg.norm(np.array(b['head'])-b['tail'])>0 for b in bones.values()))

    def test_similarity_equivariance_of_scaffold_and_depth(self):
        original=evidence();a=solve_scaffold(original,self.prior)
        theta=.4;c,s=math.cos(theta),math.sin(theta)
        transform=np.array([[2*c,-2*s,17],[2*s,2*c,-5],[0,0,1]])
        transformed=copy.deepcopy(original);transformed['source_to_model']=transform.tolist()
        b=solve_scaffold(transformed,self.prior)
        for name,point in a['landmarks'].items():
            np.testing.assert_allclose(b['landmarks'][name],(transform@np.r_[point,1])[:2],atol=1e-10)
        xy=np.array([[-.4,.7],[0,1],[.3,1.2]])
        moved=(np.c_[xy,np.ones(len(xy))]@transform.T)[:,:2]
        spec={'owner':'head','kind':'surface'}
        np.testing.assert_allclose(depth_field(moved,spec,b,self.prior),2*depth_field(xy,spec,a,self.prior),atol=1e-10)

    def test_shared_field_does_not_depend_on_batch_or_material_count(self):
        scaffold=solve_scaffold(evidence(),self.prior)
        xy=np.array([[-.4,.7],[0,1],[.3,1.2]])
        spec={'owner':'head','kind':'surface'}
        a=depth_field(xy,spec,scaffold,self.prior)
        b=np.r_[depth_field(xy[:1],spec,scaffold,self.prior),depth_field(xy[1:],spec,scaffold,self.prior)]
        np.testing.assert_array_equal(a,b)

    def test_missing_landmark_is_not_silently_fabricated(self):
        e=evidence();del e['landmarks']['knee.R']
        with self.assertRaisesRegex(ValueError,'Unresolved'):solve_scaffold(e,self.prior)

    def test_mesh_covers_domain_without_degenerate_triangles(self):
        xy,faces,_,_=regular_mesh([-3,-5,7,12],2)
        np.testing.assert_allclose(xy.min(axis=0),[-3,-5]);np.testing.assert_allclose(xy.max(axis=0),[7,12])
        a,b=xy[faces[:,1]]-xy[faces[:,0]],xy[faces[:,2]]-xy[faces[:,0]]
        areas=a[:,0]*b[:,1]-a[:,1]*b[:,0]
        self.assertTrue((areas<0).all())
        self.assertAlmostEqual(abs(areas).sum()/2,170)

    def test_no_input_mutation_and_reproducible_solution(self):
        e=evidence();before=copy.deepcopy(e)
        a=solve_scaffold(e,self.prior)
        self.assertEqual(e,before);self.assertEqual(a,solve_scaffold(e,self.prior))

    def test_reflection_is_not_accepted_as_side_calibration(self):
        e=evidence();e['source_to_model'][0][0]=-1
        with self.assertRaisesRegex(ValueError,'similarity'):solve_scaffold(e,self.prior)
