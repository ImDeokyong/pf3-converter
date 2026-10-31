import unittest
import numpy as np
from PIL import Image
from lut import Cube
from preview import Renderer, viewport_box

class TestPreview(unittest.TestCase):
    def setUp(self):
        self.image = Image.fromarray(np.random.default_rng(42).integers(0,256,(240,400,3),dtype=np.uint8))
        grid = np.stack(np.meshgrid([0.,1.],[0.,1.],[0.,1.],indexing='ij'),axis=-1).astype(np.float32)
        self.identity = Cube(grid,np.zeros(3),np.ones(3))
        self.invert = Cube(1-grid,np.zeros(3),np.ones(3))

    def test_native_pixels(self):
        box,size=viewport_box(self.image.size,(100,80),1,(200,120))
        a,b=Renderer().render(self.image,self.identity,1,1,box,size)
        np.testing.assert_array_equal(a,self.image.crop(box))
        np.testing.assert_array_equal(a,b)

    def test_fit_and_edges(self):
        box,size=viewport_box((6000,4000),(900,600),.15,(3000,2000))
        self.assertEqual(box,(0,0,6000,4000))
        self.assertEqual(size,(900,600))
        box,size=viewport_box((6000,4000),(900,600),1,(-100,9000))
        self.assertEqual(box,(0,3400,900,4000))

    def test_strength(self):
        renderer=Renderer()
        box=(0,0,400,240)
        a,b=renderer.render(self.image,self.invert,1,1,box,self.image.size)
        np.testing.assert_array_equal(np.asarray(b),255-np.asarray(a))
        a,b=renderer.render(self.image,self.invert,0,1,box,self.image.size)
        np.testing.assert_array_equal(a,b)
        a,b=renderer.render(self.image,self.invert,.5,1,box,self.image.size)
        self.assertLessEqual(np.abs(np.asarray(b).astype(float)-127.5).max(),.5)

    def test_cache_and_invalidation(self):
        renderer=Renderer()
        args=(self.image,None,1,1,(0,0,400,240),(400,240))
        pair=renderer.render(*args)
        self.assertIs(renderer.render(*args),pair)
        self.assertIsNot(renderer.render(self.image,None,1,2,args[4],args[5]),pair)
        renderer.limit=60000
        renderer.render(self.image,None,1,3,(0,0,100,100),(100,100))
        self.assertLessEqual(renderer.bytes,renderer.limit)

    def test_native_comparison_pair_preserves_pixels(self):
        altered=Image.new('RGB',self.image.size,(255,12,99))
        box,size=viewport_box(self.image.size,(100,80),1,(200,120))
        a,b=Renderer().render(self.image,None,1,10,box,size,altered)
        np.testing.assert_array_equal(a,self.image.crop(box))
        np.testing.assert_array_equal(b,altered.crop(box))

if __name__=='__main__': unittest.main()
