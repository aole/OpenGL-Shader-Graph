#!/usr/bin/env python3

import sys

__author__ = 'Bhupendra Aole'
__version__ = '0.1.0'

class Obj3D:
    def __init__( self, filename ):
        self.vertices = []
        self.normals = []
        self.faces = []

        f = open( filename )
        line=f.readline()
        while line:
            line = line.strip()
            if len(line)>2:
                # vertices
                if line[:2]=='v ':
                    vec=[float(x) for x in line[2:].split()]
                    self.vertices.append( vec )
                
                # normals
                if line[:2]=='vn ':
                    vec=[float(x) for x in line[3:].split()]
                    self.normals.append( vec )
                
                # faces
                elif line[:2]=='f ':
                    cs = line[2:].split()
                    face = []
                    for i in cs:
                        c = i.split('/')
                        face.append( ( int( c[0] )-1, int( c[2] )-1 ) )
                    self.faces.append( face )
                    
            # read next line
            line=f.readline()

    def getVerticesFlat( self ):
        v = []
        for f in self.faces:
            for i in range( 3 ):
                v.append( self.vertices[f[i][0]] )
        return v
        
if __name__ == '__main__':
    obj = Obj3D( 'testdata\cube.obj' )

    print( 'Vertices:' )
    for v in range( len( obj.vertices ) ):
        print( v, obj.vertices[v] )

    print( '\nFaces:' )
    for f in range( len( obj.faces ) ):
        print( str( f+1 ), obj.faces[f] )
        
    print( obj.getVerticesFlat() )