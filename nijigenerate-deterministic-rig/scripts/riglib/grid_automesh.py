"""Generate landmark-aligned Grid axes exclusively through native AutoMesh."""
import numpy as np


def axis_tolerance(values):
    # Account only for float64 subtraction roundoff at the existing .0003
    # boundary; this is not a relaxation for native float32 mesh error.
    return .0003+8*np.finfo(float).eps*np.maximum(1.,abs(np.asarray(values,float)))


def generate(client, target, axis_x, axis_y):
    simple={'mask_threshold':15,'x_segments':1,'y_segments':1,'margin':0.}
    client.call('AutoMesh_SetSimple_grid',**simple)
    client.call('AutoMesh_SetAdvanced_grid',scale_x=[0.,1.],scale_y=[0.,1.])
    client.call('AutoMesh_Apply_grid',context={'nodes':[target]})
    measured=client.read(target)['item']['data'];bounds={};advanced={};coalesced={}
    desired={'x':np.asarray(axis_x,float),'y':np.asarray(axis_y,float)}
    for axis in ('x','y'):
        values=np.asarray(measured['grid_axis_'+axis],float)
        if values.shape!=(2,) or not np.isfinite(values).all() or values[1]<=values[0]:
            raise ValueError('Grid AutoMesh returned degenerate alpha bounds')
        bounds[axis]=values.tolist()
        # GridDeformer.normalizeAxis merges close float32 coordinates. Sending
        # both members makes deriveAxes reject the Cartesian vertex count and
        # silently restores DefaultAxis. Express those landmarks with one
        # representable native line before asking AutoMesh to build the grid.
        rounding=8*float(np.finfo(np.float32).eps)*max(1.,float(np.max(abs(values))),float(np.max(abs(desired[axis]))))
        native=[]
        for value in sorted(desired[axis]):
            if native and value-native[-1]<=max(1e-4,1e-4*max(abs(value),abs(native[-1])))+rounding:
                continue
            native.append(float(value))
        coalesced[axis]={'requested':desired[axis].tolist(),'representable':native,'float32_roundoff_bound':rounding}
        advanced['scale_'+axis]=((np.asarray(native)-values[0])/(values[1]-values[0])).tolist()
    client.call('AutoMesh_SetAdvanced_grid',**advanced)
    client.call('AutoMesh_Apply_grid',context={'nodes':[target]})
    actual=client.read(target)['item']['data'];errors={}
    for axis in ('x','y'):
        values=np.asarray(actual['grid_axis_'+axis],float)
        if len(values)<2 or not np.isfinite(values).all() or np.any(np.diff(values)<=0):
            raise ValueError('Grid AutoMesh did not return a usable native axis array')
        errors[axis]=float(np.max(np.min(abs(desired[axis][:,None]-values[None,:]),axis=1)))
    return {'target':target,'processor':'grid','simple':simple,'advanced':advanced,
            'coordinate_authority':'carrier_local_native_precision_v1','native_axis_registration':coalesced,
            'measured_alpha_bounds':bounds,'iterations':[{'advanced':advanced,'maximum_axis_errors':errors}],
            'generated_axis_x':actual['grid_axis_x'],'generated_axis_y':actual['grid_axis_y'],
            'precision_policy':'native AutoMesh coordinates are authoritative; differences are observations, not acceptance gates',
            'direct_mesh_definition':False}
