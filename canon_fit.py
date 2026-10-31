"""Fit CUBE looks to the editable polynomial/curves consumed by Canon DPP.

The 33^3 camera tables alone are not used as the editable transform by DPP.
This is explicitly an approximation, with held-out lattice error reporting.
"""
from dataclasses import dataclass
import struct
import numpy as np
from lut import apply_cube

POWERS = ((1,0,0),(0,1,0),(0,0,1),(2,0,0),(1,1,0),(1,0,1),(0,2,0),
          (0,1,1),(0,0,2),(3,0,0),(2,1,0),(2,0,1),(1,2,0),(1,1,1),
          (1,0,2),(0,3,0),(0,2,1),(0,1,2),(0,0,3))
KNOTS = np.array([0,15,26,38,51,64,77,102,128,166,204,255], dtype=float)/255


def target_rgb(cube, rgb, strength=1.0):
    if not np.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError('Strength must be between 0 and 1')
    rgb = np.asarray(rgb, dtype=np.float32)
    return rgb*(1-strength) + np.clip(apply_cube(cube, rgb),0,1)*strength


def basis(rgb):
    r,g,b = np.moveaxis(np.asarray(rgb,dtype=float),-1,0)
    return np.stack([r**a*g**c*b**d for a,c,d in POWERS],axis=-1)


def curves_apply(rgb, curves):
    shape = rgb.shape
    flat = np.asarray(rgb).reshape(-1,3)
    return np.stack([np.interp(flat[:,i], KNOTS, curves[:,i]) for i in range(3)],-1).reshape(shape)


@dataclass
class CanonFit:
    coefficients: np.ndarray
    curves: np.ndarray
    report: dict

    def apply(self, rgb):
        return curves_apply(basis(rgb) @ self.coefficients.T, self.curves)

    def matrix_bytes(self):
        matrix = np.zeros((3,20))
        matrix[:,:19] = self.coefficients
        return np.rint(matrix*65536).astype('<i4').tobytes()

    def curve_bytes(self):
        result = b''
        for ch in range(3):
            pairs = np.stack((np.rint(KNOTS*255),np.rint(self.curves[:,ch]*255)),-1)
            result += struct.pack('<25I',12,*pairs.astype(int).ravel())
        return result


def fit_cube(cube, strength=1.0):
    axis = np.linspace(0,1,17)
    x = np.stack(np.meshgrid(axis,axis,axis,indexing='ij'),-1).reshape(-1,3)
    gray = np.repeat(np.linspace(0,1,129)[:,None],3,1)
    x = np.concatenate((x,np.tile(gray,(8,1))))
    y = target_rgb(cube,x,strength)
    features = basis(x)
    identity = np.repeat(KNOTS[:,None],3,1)
    tone = np.round(target_rgb(cube,np.repeat(KNOTS[:,None],3,1),strength)*255)/255
    # A monotonic neutral-axis shaper represents contrast, leaving hue/chroma
    # for the cubic polynomial. Other LUTs still get the identity-curve fit.
    candidates = [('matrix',identity)]
    if np.all(np.diff(tone,axis=0)>=0):
        tone[0]=0; tone[-1]=1
        candidates.append(('matrix_and_curves',tone))
    best = None
    for mode, curves in candidates:
        desired = np.stack([np.interp(y[:,i],curves[:,i],KNOTS) for i in range(3)],-1)
        coeff = np.linalg.lstsq(features,desired,rcond=None)[0]
        for _ in range(12):
            q = features@coeff
            out = curves_apply(q,curves)
            error = np.mean((out-y)**2)
            proposal = coeff.copy()
            for ch in range(3):
                derivative = (np.interp(q[:,ch]+.001,KNOTS,curves[:,ch])-
                              np.interp(q[:,ch]-.001,KNOTS,curves[:,ch]))/.002
                jac = features*derivative[:,None]
                proposal[:,ch] += np.linalg.solve(jac.T@jac+np.eye(19)*.001,jac.T@(y[:,ch]-out[:,ch]))
            for step in (1,.5,.25,.1):
                trial = coeff+(proposal-coeff)*step
                if np.max(np.abs(trial))<=32 and np.mean((curves_apply(features@trial,curves)-y)**2)<error:
                    coeff=trial
                    break
            else:
                break
        if not np.isfinite(coeff).all() or abs(coeff).max()>32:
            continue
        coeff=np.round(coeff*65536)/65536
        score=np.mean((curves_apply(features@coeff,curves)-y)**2)
        if best is None or score<best[0]:
            best=(score,mode,coeff.T,curves.copy())
    if best is None:
        raise ValueError('This LUT could not be fitted to a stable Canon transform.')
    _,mode,coeff,curves=best
    result=CanonFit(coeff,curves,{})
    # Offset lattice: not the training nodes. Metrics describe model fit, not
    # perceptual Delta E and not a camera/DPP image validation claim.
    held=(np.arange(18)+.5)/18
    check=np.stack(np.meshgrid(held,held,held,indexing='ij'),-1).reshape(-1,3)
    delta=abs(result.apply(check)-target_rgb(cube,check,strength))*255
    result.report={'method':mode,'approximation':True,'validation_samples':len(check),
                   'estimated_rgb_mae_255':float(delta.mean()),
                   'estimated_rgb_p95_255':float(np.percentile(delta,95)),
                   'estimated_rgb_max_255':float(delta.max()),
                   'native_render_verified':False,'camera_tested':False}
    return result
