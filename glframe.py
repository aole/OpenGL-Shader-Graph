
import numpy as np
from readobj import Obj3D
from shadergraph import NodeFactory, ShaderGraph
import time

import wx
from wx import glcanvas

from utils import ortho, perspective, translate, rotate

from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.arrays import vbo
from OpenGL.GL import shaders

REALTIME = False
RENDER_BACKGROUND = True
RENDER_FOREGROUND = True

File3D = 'cube.obj'

vertexBGShader = """
#version 330

layout(location = 0) in vec3 Vertex;
uniform mat4 MVP;

void main() {
    gl_Position = MVP * vec4( Vertex, 1 );
}
    """

fragmentBGShader = """
#version 330

out vec4 sg_FragColor;

void main() {
    vec2 d = gl_FragCoord.xy/30;
    if( mod(int(d.x),2) == mod(int(d.y), 2) ) {
        sg_FragColor = vec4( .7, .7, .7, 1 );
    }
    else {
        sg_FragColor = vec4( .3, .3, .3, 1 );
    }
}
"""

custom_fs_nodes = {
    'sg_ScreenSize':('Screen Size', [('Width', 'float', 'sg_ScreenSize.x'), ('Height', 'float', 'sg_ScreenSize.y')], 'vec2','self.GetGLExtents()', glUniform2f),
    'sg_Time':('Time', [('time', 'float', 'sg_Time')], 'float','[time.clock()]', glUniform1f),
}

custom_vs_nodes = {
    'MVP':('MVP Matrix', [('Matrix', 'mat4', 'MVP')], 'mat4', 'self.getMVP()', glUniformMatrix4fv),
}

# Add custom nodes to the node factory
for value in custom_vs_nodes.values():
    NodeFactory.addCustomNode(value[0], value[1])
for value in custom_fs_nodes.values():
    NodeFactory.addCustomNode(value[0], value[1])

class GLFrame( glcanvas.GLCanvas ):
    """A simple class for using OpenGL with wxPython."""
    
    near_plane = 0.1
    far_plane = 100
    world_pos = (0, 0, -6)
    world_rot = (0, 0, 0)
    
    def __init__(self, parent, graph):
        self.GLinitialized = False
        attribList = (glcanvas.WX_GL_RGBA, # RGBA
                      glcanvas.WX_GL_DOUBLEBUFFER, # Double Buffered
                      glcanvas.WX_GL_DEPTH_SIZE, 24) # 24 bit

        super().__init__( parent, attribList=attribList )

        #
        # Create the canvas
        self.context = glcanvas.GLContext( self )
        self.SetCurrent( self.context )

        self.left_down = False
        
        #
        # Set the event handlers.
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.processEraseBackgroundEvent)
        self.Bind(wx.EVT_SIZE, self.processSizeEvent)
        self.Bind(wx.EVT_PAINT, self.processPaintEvent)
        self.Bind(wx.EVT_MOUSEWHEEL, self.processWheelEvent)
        self.Bind(wx.EVT_MOTION, self.processMotion)
        self.Bind(wx.EVT_LEFT_DOWN, self.processLeftDown)
        self.Bind(wx.EVT_LEFT_UP, self.processLeftUp)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.processPaintEvent)

        self.graph = graph
        
    def GetGraph(self):
        return self.graph
        
    def SetGraph(self, graph):
        self.graph = graph
        self.graph.requires_compilation = True
        
    def processEraseBackground(self, event):
        pass # Do nothing, to avoid flashing on MSW.

    #
    # Canvas Proxy Methods

    def GetGLExtents(self):
        """Get the extents of the OpenGL canvas."""
        return self.GetClientSize()

    #
    # wxPython Window Handlers

    def processLeftDown( self, event ):
        self.last_pos = event.GetPosition()
        self.left_down = True
        self.CaptureMouse()
        
    def processLeftUp( self, event ):
        self.left_down = False
        self.ReleaseMouse()
        
    def processMotion( self, event ):
        if self.left_down:
            pos = event.GetPosition()
            diff = (pos-self.last_pos)
            self.world_rot = ( self.world_rot[0]+diff[1], self.world_rot[1]+diff[0], self.world_rot[2] )
            self.last_pos = pos
            self.Refresh( False )
        
    def processWheelEvent( self, event ):
        delta = event.GetWheelRotation() / 100
        self.world_pos = ( self.world_pos[0], self.world_pos[1], self.world_pos[2]+delta )
        
    def processEraseBackgroundEvent( self, event ):
        """Process the erase background event."""
        pass # Do nothing, to avoid flashing on MSWin

    def processSizeEvent( self, event ):
        self.Show()
        #self.SetCurrent( self.context )

        width, height = self.GetGLExtents()
        self.OnReshape( width, height )

    def processPaintEvent(self, event):
        # This is a 'perfect' time to initialize OpenGL ... only if we need to
        if not self.GLinitialized:
            self.OnInitGL()
            self.GLinitialized = True

        if self.graph.requires_compilation:
            self.compileFGShaders()
        self.OnPaintGL()
        event.Skip()

    #
    # GLFrame OpenGL Event Handlers

    def OnInitGL(self):
        """Initialize OpenGL for use in the window."""
        glClearColor(1, 1, 1, 1)

        # setup transparency
        #glDisable(GL_CULL_FACE)
        glEnable(GL_CULL_FACE)
        #glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND);
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
        
        width, height = self.GetGLExtents()
        bgdata = [[width,height,0.],  [0.,height,0.],  [width,0.,0.],  [0.,0.,0.]]
        self.bgvbo = vbo.VBO( np.array( bgdata, 'f' ) )
        
        self.compileBGShaders()
        
        cube = Obj3D( File3D )
        fgdata = cube.getVerticesAndNormalsFlat()
        self.fgvbo = vbo.VBO( np.array( fgdata, 'f' ) )
        
        self.compileFGShaders()
        
        if REALTIME:
            self.timer.Start(1000/60)    # 1 second interval
        
    def compileBGShaders(self):
        try:
            VERTEX_SHADER = shaders.compileShader( vertexBGShader, GL_VERTEX_SHADER )
            FRAGMENT_SHADER = shaders.compileShader( fragmentBGShader, GL_FRAGMENT_SHADER )
            
            self.bgshader = shaders.compileProgram( VERTEX_SHADER, FRAGMENT_SHADER )
        except Exception as err:
            print(err)
            
    def generateCode( self ):
        # vertex shader
        code = ""
        globalcode = ""
        self.graph.prepare()
        code, globalcode = self.graph.getVertexShaderNode().generateCode('Vertex Position', code, globalcode)
        
        vertexShader = "#version 330\n\n"
        
        vertexShader += globalcode
        
        for name, value in custom_vs_nodes.items():
            vertexShader += 'uniform '+value[2]+' '+name+';\n'
        
        vertexShader += "\nvoid main() {\n"
        vertexShader += code
        vertexShader += "}\n"
        
        # fragment shader
        code = ""
        globalcode = ""
        self.graph.prepare()
        code, globalcode = self.graph.getFragmentShaderNode().generateCode('Pixel Color', code, globalcode)
        
        fragmentShader = "#version 330\n\n"
        
        fragmentShader += globalcode
        
        for name, value in custom_fs_nodes.items():
            fragmentShader += 'uniform '+value[2]+' '+name+';\n'
            
        fragmentShader += "\nvoid main() {\n"
        fragmentShader += code
        fragmentShader += "}\n"
        
        return vertexShader, fragmentShader
        
    def compileFGShaders(self):
        try:
            vertexShader, fragmentShader = self.generateCode()
            
            # Vertex Shader
            print('====Vertex Shader======')
            print(vertexShader)
            print('====================')
            VERTEX_SHADER = shaders.compileShader( vertexShader, GL_VERTEX_SHADER )
        
            # Fragment Shader
            print('====Fragment Shader====')
            print(fragmentShader)
            print('====================')
            FRAGMENT_SHADER = shaders.compileShader( fragmentShader, GL_FRAGMENT_SHADER )
            
            self.fgshader = shaders.compileProgram( VERTEX_SHADER, FRAGMENT_SHADER )

            self.graph.requires_compilation = False
            self.graph.in_error = False
        except Exception as err:
            self.graph.requires_compilation = False
            self.graph.in_error = True
            print(err)
            
        print('compiled')
            
    def OnReshape( self, width, height ):
        """Reshape the OpenGL viewport based on the dimensions of the window."""
        glViewport( 0, 0, width, height )
        
        if self.GLinitialized:
            bgdata = [[width,height,0.],  [0.,height,0.],  [width,0.,0.],  [0.,0.,0.]]
            if self.bgvbo:
                self.bgvbo.delete()
            self.bgvbo = vbo.VBO( np.array( bgdata, 'f' ) )
        
    def getMVP( self ):
        width, height = self.GetGLExtents()
        MVP = perspective(45.0, width / height, self.near_plane, self.far_plane);
        
        MVP = translate( MVP, self.world_pos[0], self.world_pos[1], self.world_pos[2] )
        MVP = rotate( MVP, self.world_rot[1], 0, 1, 0 )
        MVP = rotate( MVP, self.world_rot[0], 1, 0, 0 )
        
        return (1, True, MVP)
        
    def OnPaintGL( self ):
        glClear( GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT )

        width, height = self.GetGLExtents()
        
        if RENDER_BACKGROUND:
            MVP = ortho( 0,width, 0, height, -1, 1 )
            
            shaders.glUseProgram( self.bgshader )
            
            glUniformMatrix4fv( glGetUniformLocation(self.bgshader, 'MVP'), 1, True, MVP )
            
            self.bgvbo.bind()
            glEnableClientState( GL_VERTEX_ARRAY );
            glVertexPointerf( self.bgvbo )
            
            glDrawArrays( GL_TRIANGLE_STRIP, 0, len( self.bgvbo ) )
            
            self.bgvbo.unbind()
            glDisableClientState( GL_VERTEX_ARRAY );
        
        if RENDER_FOREGROUND:
            shaders.glUseProgram( self.fgshader )
            
            self.fgvbo.bind()
            glEnableVertexAttribArray( 0 )
            glEnableVertexAttribArray( 1 )
            glVertexAttribPointer( 0, 3, GL_FLOAT, GL_FALSE, 24, self.fgvbo )
            glVertexAttribPointer( 1, 3, GL_FLOAT, GL_FALSE, 24, self.fgvbo+12 )
            
            for uname, ucount, ufuncs in self.graph.uniforms.values():
                UNIFORM_FUNCTION[ucount]( glGetUniformLocation(self.fgshader, uname), *ufuncs() )
            
            for name, value in custom_vs_nodes.items():
                value[4]( glGetUniformLocation(self.fgshader, name), *eval(value[3]) )
                
            for name, value in custom_fs_nodes.items():
                value[4]( glGetUniformLocation(self.fgshader, name), *eval(value[3]) )
                
            glDrawArrays( GL_TRIANGLES, 0, len( self.fgvbo ) )
            
            self.fgvbo.unbind()
            glDisableVertexAttribArray( 0 )
            glDisableVertexAttribArray( 1 )
        
        shaders.glUseProgram( 0 )
        
        self.SwapBuffers()
        
if __name__=='__main__':
    a = wx.App()
    f = wx.Frame(None)
    gf = GLFrame(f, ShaderGraph())
    f.Show()

    a.MainLoop()
    a.Destroy()
    
    