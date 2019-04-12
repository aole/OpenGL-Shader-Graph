import wx
import numpy as np
import time
import random

from wx import glcanvas

from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.arrays import vbo
from OpenGL.GL import shaders

from readobj import Obj3D

__author__ = 'Bhupendra Aole'
__version__ = '0.1.0'

vertexShader = """
    #version 120
    void main() {
        gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
    }
    """

fragmentShader = """
    #version 120
    void main() {
        gl_FragColor = vec4( .9, .9, .9, 1 );
    }
    """

uniforms = {}
UNIFORM_FUNCTION = [None, glUniform1f, glUniform2f, glUniform3f, glUniform4f]

class Plug:
    count = 1
    def __init__(self, name, parent, type, variable, value, generate_variable=True, display=True):
        self.name = name
        self.parent = parent
        self.type = type
        self.variable = variable
        self.value = value
        self.defaltValue = value
    
        if generate_variable:
            self.variable += str(Plug.count)
            Plug.count += 1
        
        self.display = display
        
    def __str__(self):
        if type(self.value)==Plug:
            return f'{self.type} {self.variable} = {self.value.variable}'
        else:
            return f'{self.type} {self.variable} = {self.value}'
        
    def setValue(self, value):
        self.value = value
        
        
class Value:
    def __init__(self):
        self.parent = None
        
    def __repr__(self):
        return self.__str__()
        
class ColorValue(Value):
    def __init__(self, color=(1,1,1,1)):
        super().__init__()
        self.color = color
        
    def __str__(self):
        return f'vec4({self.color[0]}, {self.color[1]}, {self.color[2]}, {self.color[3]})'
    
class FloatValue(Value):
    def __init__(self, value=0.5):
        super().__init__()
        self.value = value
        
    def __str__(self):
        return f'{self.value}'
    
class Node:
    def __init__( self, name='Node' ):
        self.inplugs = {}
        self.outplugs = {}
        self.codeGenerated = False
        self.name = name
        self.active = True
        self.location = [0,0]
        
    def addInPlug(self, plug):
        self.inplugs[plug.name] = plug
        
    def addOutPlug(self, plug):
        self.outplugs[plug.name] = plug
        
    def setValue(self, name, plug):
        self.inplugs[name].setValue(plug)
        
    def getInPlug(self, name):
        return self.inplugs[name]
        
    def getOutPlug(self, name):
        return self.outplugs[name]
        
    def __str__(self):
        return str(type(self))
        
    def generateCode(self, name, code, globalcode):
        if self.codeGenerated == True:
            return code
        
        print('gencode', name, self)
        for plugname, plug in self.inplugs.items():
            print('\t', plugname, type(plug))
            if isinstance(plug.value, Plug) and plug.value.parent!=self:
                if isinstance(plug.value.parent, UniformNode):
                    print('\tuniformfloat:', type(plug.value.value))
                    globalcode += plug.value.value + ";\n"
                else:
                    out, gc = plug.value.parent.generateCode(plug.value.name, code, globalcode)
                    print('adding code:', plug.value.parent.name,'.',plug.value.name,':',out)
                    code = out
                    globalcode = gc
            
            out = f'\t{plug};\n'
            print('adding code2:', plugname, ':', out)
            code += out
        code += self.customCode(name)
        
        self.codeGenerated = True
        
        return code, globalcode
        
    def customCode(self, name):
        return f'\t{self.outplugs[name]};\n'
        
class UniformNode(Node):
    def __init__(self, name, type, count, function):
        super().__init__(name)
        
        uniforms[name] = (UNIFORM_FUNCTION[count], function)
        
        self.plug = Plug('Uniform', self, type, name, "uniform "+type+" "+name, False)
        self.addOutPlug(self.plug)
        
    def __str__(self):
        return self.plug.value
        
    def __repr__(self):
        return self.__str__()
        
class UniformRandomFloatNode(UniformNode):
    def __init__(self, name):
        super().__init__(name, 'float', 1, UniformRandomFloatNode.getRandomFloat)
        
    def getRandomFloat():
        return [random.random()]
        
class UniformRandomColorNode(UniformNode):
    def __init__(self, name):
        super().__init__(name, 'vec4', 4, UniformRandomColorNode.getRandomColor)
        
    def getRandomColor():
        return (random.random(), random.random(), random.random(), 1)
        
class ScaleNode(Node):
    def __init__(self):
        super().__init__('Scale')
        
        self.addInPlug(Plug('ScaleFloat', self, 'float', 'scale', FloatValue()))
        self.addInPlug(Plug('ScaleInColor', self, 'vec4', 'color', ColorValue()))
        self.addOutPlug(Plug('ScaleOutColor', self, 'vec4', 'color', ColorValue()))
        
    def customCode(self, name):
        return f'\tvec4 {self.outplugs["ScaleOutColor"].variable} = {self.inplugs["ScaleInColor"].variable} * {self.inplugs["ScaleFloat"].variable};\n'
        
class InvertColorNode(Node):
    def __init__(self):
        super().__init__('Invert Color')
        
        self.inplugs['inColor'] = Plug('inColor', self, 'vec4', 'color', ColorValue())
        self.outplugs['outColor'] = Plug('outColor', self, 'vec4', 'color', self.inplugs['inColor'])
        
    def customCode(self, name):
        return f'\tvec4 {self.outplugs["outColor"].variable} = vec4(1-{self.inplugs["inColor"].variable}.r, 1-{self.inplugs["inColor"].variable}.g, 1-{self.inplugs["inColor"].variable}.b, {self.inplugs["inColor"].variable}.a);\n'
        
class SolidColorNode(Node):
    def __init__(self):
        super().__init__('Solid Color')
        
        self.outplugs['Color'] = Plug('Color', self, 'vec4', 'color', ColorValue((.1, .3, .7, 1)))
        
class FragmentShaderNode(Node):
    def __init__(self):
        super().__init__('Fragment Shader')
        
        self.inplugs['Color'] = Plug('Color', self, 'vec4', 'color', ColorValue())
        self.outplugs['gl_FragColor'] = Plug('gl_FragColor', self, '', 'gl_FragColor', self.inplugs['Color'], False, False)
        
class FragmentShaderGraph:
    def __init__(self):
        fsnode = FragmentShaderNode()
        fsnode.location = [150, 20]
        #solidcolor = SolidColorNode()
        scalecolor = ScaleNode()
        scalecolor.location = [50, 20]
        unicolor = UniformRandomColorNode('Random Color')
        unicolor.location = [50, 100]
        unitime = UniformRandomFloatNode('Time')
        unitime.location = [50, 160]
        #invcolor = InvertColorNode()
        
        #scalecolor.setValue('ScaleInColor', unicolor.getOutPlug('Uniform'))
        #scalecolor.setValue('ScaleFloat', unitime.getOutPlug('Uniform'))
        fsnode.setValue('Color', scalecolor.getOutPlug('ScaleOutColor'))
        
        self.nodes = [fsnode, scalecolor, unicolor, unitime]
        
    def compile(self):
        code = ""
        globalcode = ""
        code, globalcode = self.nodes[0].generateCode('gl_FragColor', code, globalcode)
        
        fragmentShader = "#version 330\n\n"
        fragmentShader += globalcode
        fragmentShader += "\nvoid main() {\n"
        fragmentShader += code
        fragmentShader += "}"
        
        print('====================')
        print(fragmentShader)
        print('====================')
        return shaders.compileShader( fragmentShader, GL_FRAGMENT_SHADER )
        
class GLFrame( glcanvas.GLCanvas ):
    """A simple class for using OpenGL with wxPython."""
    
    near_plane = 0.1
    far_plane = 100
    world_pos = (0, 0, -6)
    world_rot = (0, 0, 0)
    
    def __init__(self, parent):
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
        #self.Bind(wx.EVT_IDLE, self.processPaintEvent)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.processEraseBackground)
        self.Bind(wx.EVT_MOUSEWHEEL, self.processWheelEvent)
        self.Bind(wx.EVT_MOTION, self.processMotion)
        self.Bind(wx.EVT_LEFT_DOWN, self.processLeftDown)
        self.Bind(wx.EVT_LEFT_UP, self.processLeftUp)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.processPaintEvent)

        self.FragmentShaderGraph = FragmentShaderGraph()
    
    def GetGraph(self):
        return self.FragmentShaderGraph
        
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
        
    def processLeftUp( self, event ):
        self.left_down = False
        
    def processMotion( self, event ):
        if self.left_down:
            pos = event.GetPosition()
            diff = (pos-self.last_pos)
            self.world_rot = ( self.world_rot[0]+diff[1], self.world_rot[1]+diff[0], self.world_rot[2] )
            # print(  )
            self.last_pos = pos
            self.Refresh( False )
        
    def processWheelEvent( self, event ):
        delta = event.GetWheelRotation() / 100
        self.world_pos = ( self.world_pos[0], self.world_pos[1], self.world_pos[2]+delta )
        #self.Refresh( False )
        
    def processEraseBackgroundEvent( self, event ):
        """Process the erase background event."""
        pass # Do nothing, to avoid flashing on MSWin

    def processSizeEvent( self, event ):
        self.Show()
        #self.SetCurrent( self.context )

        size = self.GetGLExtents()
        self.OnReshape( size.width, size.height )
        #self.Refresh( False )
        event.Skip()

    def processPaintEvent(self, event):
        #self.SetCurrent( self.context )

        # This is a 'perfect' time to initialize OpenGL ... only if we need to
        if not self.GLinitialized:
            self.OnInitGL()
            self.GLinitialized = True

        self.OnDraw()
        event.Skip()

    #
    # GLFrame OpenGL Event Handlers

    def OnInitGL(self):
        """Initialize OpenGL for use in the window."""
        glClearColor(1, 1, 1, 1)

        VERTEX_SHADER = shaders.compileShader( vertexShader, GL_VERTEX_SHADER )
        
        FRAGMENT_SHADER = self.FragmentShaderGraph.compile()
        #FRAGMENT_SHADER = shaders.compileShader( fragmentShader, GL_FRAGMENT_SHADER )
        
        self.shader = shaders.compileProgram( VERTEX_SHADER, FRAGMENT_SHADER )

        cube = Obj3D( 'cube.obj' )
        data = cube.getVerticesFlat()
        self.vbo = vbo.VBO( np.array( data, 'f' ) )
        
        self.timer.Start(1000/60)    # 1 second interval
        
    def OnReshape( self, width, height ):
        """Reshape the OpenGL viewport based on the dimensions of the window."""
        glViewport( 0, 0, width, height )
        
        glMatrixMode( GL_PROJECTION )
        glLoadIdentity()
        # glOrtho( -0.5, 0.5, -0.5, 0.5, -1, 1 )
        gluPerspective( 45.0, width/height, self.near_plane, self.far_plane )

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    def OnDraw( self ):
        glPushMatrix()
        glTranslate( self.world_pos[0], self.world_pos[1], self.world_pos[2] )
        glRotated( self.world_rot[1], 0, 1, 0 )
        glRotated( self.world_rot[0], 1, 0, 0 )
        
        glClear( GL_COLOR_BUFFER_BIT )
        
        shaders.glUseProgram( self.shader )
        self.vbo.bind()
        glEnableClientState( GL_VERTEX_ARRAY );
        glVertexPointerf( self.vbo )
        
        for uname, ufuncs in uniforms.items():
            ufuncs[0]( glGetUniformLocation(self.shader, uname), *ufuncs[1]() )
        
        glDrawArrays( GL_TRIANGLES, 0, len( self.vbo ) )
        self.vbo.unbind()
        glDisableClientState( GL_VERTEX_ARRAY );
        shaders.glUseProgram( 0 )
        
        glPopMatrix()
        
        self.SwapBuffers()
        
class GraphWindow( wx.Panel ):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        
        self.graph = None
        self.nodeRects = {}
        self.pluglocation = {}
        self.left_down = False
        self.selected_node = None
        self.lastx = self.lasty = 0
        
        self.BLACK_BRUSH = wx.Brush(wx.Colour(0,0,0))

        self.InitUI()

    def InitUI(self):
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)

        #POPUP MENU
        self.popupMenu = wx.Menu()
        self.popupMenu.Append( wx.ID_OPEN, '&Open\tCtrl+O', 'Open file' )
        self.popupMenu.Append( wx.ID_EXIT, 'E&xit\tCtrl+Q', 'Exit Application' )
        
    def SetGraph(self, graph):
        self.graph = graph
        
    def OnPaint(self, e):
        dc = wx.PaintDC(self)
        
        if self.graph:
            for node in self.graph.nodes:
                if node.active:
                    # draw with full intensity
                    intensity = 1
                else:
                    # draw with half intensity
                    intensity = 0.5
                
                locx, locy = node.location
                
                # get max name length
                nodename = node.name
                txtwidth, txtheight = dc.GetTextExtent(nodename)
                
                plugcount = 0
                for key, plug in {**node.outplugs, **node.inplugs}.items():
                    if not plug.display:
                        continue
                        
                    plugcount += 1
                    name = str(key)
                    w, h = dc.GetTextExtent(name)
                    if w > txtwidth:
                        txtwidth = w
                
                # print name
                dc.DrawRoundedRectangle(locx, locy, txtwidth+4+15, txtheight+4, 3)
                dc.DrawText(nodename, locx+2, locy+2)
            
                # print body
                bodyh = plugcount * (txtheight+4)
                dc.DrawRoundedRectangle(locx, locy+txtheight+4, txtwidth+4+15, bodyh, 3)

                #if node not in self.nodeRects:
                self.nodeRects[node] = [locx, locy, txtwidth+4+15, txtheight+4+bodyh]
                    
                y = locy+txtheight+4
                # out plugs
                for key, plug in node.outplugs.items():
                    if not plug.display:
                        continue
                        
                    y += 2
                    name = str(key)
                    w, h = dc.GetTextExtent(name)
                    dc.DrawText(name, locx+2 + (txtwidth+11-w), y)
                    dc.DrawCircle(locx+2+txtwidth+6+10, y+h/2, 3)
                    self.pluglocation[(node, plug)] = (locx+2+txtwidth+6+10, y+h/2)
                    y += txtheight
                    
                # in plugs
                for key, plug in node.inplugs.items():
                    if not plug.display:
                        continue
                        
                    y += 2
                    name = str(key)
                    w, h = dc.GetTextExtent(name)
                    dc.DrawText(name, locx+6, y)
                    dc.DrawCircle(locx, y+h/2, 3)
                    self.pluglocation[(node, plug)] = (locx, y+h/2)
                    y += txtheight
                    
            # draw connections
            for node in self.graph.nodes:
                for plug in node.inplugs.values():
                    if not plug.display:
                        continue
                        
                    x1, y1 = self.pluglocation[(node, plug)]
                    if isinstance(plug, Plug) and plug.value.parent and plug.value.parent!= node:
                        x2, y2 = self.pluglocation[(plug.value.parent, plug.value)]
                        dc.DrawLine(x1, y1, x2, y2)
                        dc.SetBrush(self.BLACK_BRUSH)
                        dc.DrawCircle(x1, y1, 3)
                        dc.DrawCircle(x2, y2, 3)
                        
    def OnSize(self, e):
        self.Refresh()

    def OnRightDown(self, event):
        self.PopupMenu( self.popupMenu, event.GetPosition() )

    def OnMouseMotion(self, event):
        x, y = event.GetPosition()
        if self.left_down:
            if self.selected_node:
                self.selected_node.location[0] += x - self.lastx
                self.selected_node.location[1] += y - self.lasty
                self.Refresh()
        else:
            for key, loc in self.pluglocation.items():
                node, plug = key
                lx, ly = loc
                if x>=lx-3 and x<=lx+3 and y>=ly-3 and y<=ly+3:
                    print(node, '->', plug)
                    
        self.lastx, self.lasty = x, y
        
    def OnLeftUp(self, event):
        self.left_down = False
        
    def OnLeftDown(self, event):
        x, y = event.GetPosition()
        self.selected_node = None
        for key, r in self.nodeRects.items():
            if x>=r[0] and x<=r[0]+r[2] and y>=r[1] and y<=r[1]+r[3]:
                self.selected_node = key
        
        self.left_down = True
        self.lastx, self.lasty = x, y
        
class Window( wx.Frame ):
    def __init__( self, *args, **kwargs ):
        super().__init__( *args, **kwargs )
        self.initUI()
    
    def initUI( self ):
        # MENU
        fmenu = wx.Menu()
        
        fitem = fmenu.Append( wx.ID_OPEN, '&Open\tCtrl+O', 'Open file' )
        self.Bind( wx.EVT_MENU, self.onOpen, fitem )
        
        fmenu.AppendSeparator()
        fitem = fmenu.Append( wx.ID_EXIT, 'E&xit\tCtrl+Q', 'Exit Application' )
        self.Bind(wx.EVT_MENU, self.onQuit, fitem)
        
        mbar = wx.MenuBar()
        mbar.Append( fmenu, '&File' )
        
        self.SetMenuBar( mbar )
        
        # BACK PANEL
        backPanel = wx.Panel(self, wx.ID_ANY)
        
        # GL WINDOW
        glwindow = GLFrame(backPanel)
        
        # GRAPH PANEL
        graphPanel = GraphWindow( backPanel, wx.ID_ANY )
        #text = wx.StaticText( self.graphPanel, wx.ID_ANY, label='Boilerplate Code', pos=( 10, 10 ) )
        graphPanel.SetGraph( glwindow.GetGraph() )
        
        # LAYOUT
        gridSizer = wx.GridSizer(rows=1, cols=2, hgap=5, vgap=5)
        gridSizer.Add(graphPanel, 0, wx.EXPAND)
        gridSizer.Add(glwindow, 0, wx.EXPAND)
        
        backPanel.SetSizer(gridSizer)
        
        # MIN SIZE
        self.SetSizeHints(400,300,-1,-1)
        gridSizer.Fit(self)
        
        # SHOW
        self.Show()
        
    def onQuit( self, event ):
        self.Close()
        
    def onOpen( self, event ):
        print( 'open' )
        
class Application( wx.App ):
    def run( self ):
        frame = Window(None, wx.ID_ANY, 'OpenGL Shader Graph')
        frame.Show()

        self.MainLoop()
        self.Destroy()
        
Application().run()