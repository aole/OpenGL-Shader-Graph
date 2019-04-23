import math
import numpy as np

def ortho(left, right, bot, top, near, far):
    dx, dy, dz = right - left, top - bot, far - near
    rx, ry, rz = -(right+left) / dx, -(top+bot) / dy, -(far+near) / dz
    return np.array([[2/dx, 0,    0,     rx],
                     [0,    2/dy, 0,     ry],
                     [0,    0,    -2/dz, rz],
                     [0,    0,    0,     1]], 'f')

def perspective(fovy, aspect, near, far):
    scale = 1.0/math.tan(math.radians(fovy)/2.0)
    sx, sy = scale / aspect, scale
    zz = (far + near) / (near - far)
    zw = 2 * far * near/(near - far)
    return np.array([[sx, 0,  0,  0],
                     [0,  sy, 0,  0],
                     [0,  0, zz, zw],
                     [0,  0, -1,  0]], 'f')

def translate(mat, x=0.0, y=0.0, z=0.0):
    matrix = np.identity(4, 'f')
    matrix[:3, 3] = (x, y, z)
    return np.matmul(mat, matrix)

def rotate(mat, angle, x, y, z):
    l = math.sqrt(x**2+y**2+z**2)
    x, y, z = x/l, y/l, z/l
    radians = math.radians(angle)
    s, c = math.sin(radians), math.cos(radians)
    nc = 1 - c
    matrix = np.array([[x*x*nc + c,   x*y*nc - z*s, x*z*nc + y*s, 0],
                     [y*x*nc + z*s, y*y*nc + c,   y*z*nc - x*s, 0],
                     [x*z*nc - y*s, y*z*nc + x*s, z*z*nc + c,   0],
                     [0,            0,            0,            1]], 'f')
    return np.matmul(mat, matrix)
    
if __name__ == '__main__':
    m = perspective(45.0, 3/4, 1, 1000)
    print( m )
    m = translate(m, 5, 2)
    print( m )
    m = rotate(m, 10, 1, 0, 0)
    print( m )
    