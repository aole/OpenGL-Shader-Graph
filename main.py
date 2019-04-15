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

from shadergraph import uniforms, Plug, FragmentShaderGraph

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

        if self.FragmentShaderGraph.requires_compilation:
            self.compileShaders()
            
        self.OnDraw()
        event.Skip()

    #
    # GLFrame OpenGL Event Handlers

    def OnInitGL(self):
        """Initialize OpenGL for use in the window."""
        glClearColor(1, 1, 1, 1)

        cube = Obj3D( 'cube.obj' )
        data = cube.getVerticesFlat()
        self.vbo = vbo.VBO( np.array( data, 'f' ) )
        
        self.FragmentShaderGraph.build()
        self.compileShaders()
        
        self.timer.Start(1000/60)    # 1 second interval
        
    def compileShaders(self):
        VERTEX_SHADER = shaders.compileShader( vertexShader, GL_VERTEX_SHADER )
        
        # Fragment Shader
        code = ""
        globalcode = ""
        code, globalcode = self.FragmentShaderGraph.nodes[0].generateCode('gl_FragColor', code, globalcode)
        
        fragmentShader = "#version 330\n\n"
        fragmentShader += globalcode
        fragmentShader += "\nvoid main() {\n"
        fragmentShader += code
        fragmentShader += "}"
        
        print('====================')
        print(fragmentShader)
        print('====================')
        FRAGMENT_SHADER = shaders.compileShader( fragmentShader, GL_FRAGMENT_SHADER )
        
        self.shader = shaders.compileProgram( VERTEX_SHADER, FRAGMENT_SHADER )

        self.FragmentShaderGraph.requires_compilation = False
        
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
        self.selected_plug = None
        self.selected_plug2 = None
        self.lastx = self.lasty = 0
        
        self.BLACK_BRUSH = wx.Brush(wx.Colour(0,0,0))
        self.RED_BRUSH = wx.Brush(wx.Colour(255,0,0))
        self.BLACK_PEN = wx.Pen(wx.Colour(0,0,0))
        self.RED_PEN = wx.Pen(wx.Colour(255,0,0))
        
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        
        self.InitUI()

    def InitUI(self):
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
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
        
    def OnEraseBackground(self, event):
        pass
        
    def OnPaint(self, event):
        #dc = wx.PaintDC(self)
        dc = wx.AutoBufferedPaintDC(self)
        dc.Clear()
        
        if self.graph:
            for node in self.graph.nodes:
                if node.active:
                    # draw with full intensity
                    intensity = 1
                else:
                    # draw with half intensity
                    intensity = 0.5
                
                locx, locy = node.location
                dc.SetPen(self.BLACK_PEN)
                
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
                    if plug==self.selected_plug or plug==self.selected_plug2:
                        dc.SetPen(self.RED_PEN)
                    else:
                        dc.SetPen(self.BLACK_PEN)
                    dc.DrawText(name, locx+2 + (txtwidth+11-w), y)
                    dc.DrawCircle(locx+2+txtwidth+6+10, y+h/2, 3)
                    self.pluglocation[plug] = (locx+2+txtwidth+6+10, y+h/2)
                    y += txtheight
                    
                # in plugs
                for key, plug in node.inplugs.items():
                    if not plug.display:
                        continue
                        
                    y += 2
                    name = str(key)
                    w, h = dc.GetTextExtent(name)
                    if plug==self.selected_plug or plug==self.selected_plug2:
                        dc.SetPen(self.RED_PEN)
                    else:
                        dc.SetPen(self.BLACK_PEN)
                    dc.DrawText(name, locx+6, y)
                    dc.DrawCircle(locx, y+h/2, 3)
                    self.pluglocation[plug] = (locx, y+h/2)
                    y += txtheight
                    
            # draw connections
            dc.SetPen(self.BLACK_PEN)
            for node in self.graph.nodes:
                for plug in node.inplugs.values():
                    if not plug.display:
                        continue
                        
                    x1, y1 = self.pluglocation[plug]
                    if isinstance(plug, Plug) and plug.value.parent and plug.value.parent!= node:
                        x2, y2 = self.pluglocation[plug.value]
                        dc.DrawLine(x1, y1, x2, y2)
                        
                        dc.SetBrush(self.BLACK_BRUSH)
                        if plug == self.selected_plug or plug == self.selected_plug2:
                            dc.SetBrush(self.RED_BRUSH)
                        dc.DrawCircle(x1, y1, 3)
                        
                        dc.SetBrush(self.BLACK_BRUSH)
                        if plug.value == self.selected_plug or plug.value == self.selected_plug2:
                            dc.SetBrush(self.RED_BRUSH)
                        dc.DrawCircle(x2, y2, 3)
                        
            # hovered plug
            if self.selected_plug:
                x1, y1 = self.pluglocation[self.selected_plug]
                x2, y2 = self.ScreenToClient(wx.GetMousePosition())
                dc.DrawLine(x1, y1, x2, y2)
                
    def OnSize(self, e):
        self.Refresh()

    def OnRightDown(self, event):
        self.PopupMenu( self.popupMenu, event.GetPosition() )

    def OnMouseMotion(self, event):
        x, y = event.GetPosition()
        
        self.selected_plug2 = None
        found = False
        for plug, loc in self.pluglocation.items():
            lx, ly = loc
            if x>=lx-3 and x<=lx+3 and y>=ly-3 and y<=ly+3:
                if self.left_down and self.selected_plug:
                    self.selected_plug2 = plug
                    found = True
                elif not self.left_down:
                    self.selected_plug = plug
                    found = True
                break
                
        if not found and not self.left_down:
            self.selected_plug = None
            
        if self.left_down:
            if self.selected_node:
                self.selected_node.location[0] += x - self.lastx
                self.selected_node.location[1] += y - self.lasty
                    
        self.Refresh()
        self.lastx, self.lasty = x, y
        
    def OnLeftUp(self, event):
        self.left_down = False
        
        if self.selected_plug and self.selected_plug2:
            pin = self.selected_plug
            pout = self.selected_plug2
            if pin not in pin.parent.inplugs.values():
                pin, pout = pout, pin
            if pin in pin.parent.inplugs.values() and pout in pout.parent.outplugs.values():
                pin.setValue(pout)
                self.graph.requires_compilation = True
            else:
                print('no join:', pin in pin.parent.inplugs, pout in pout.parent.outplugs)
        else:
            print(self.selected_plug, self.selected_plug2)
            
        self.selected_plug = self.selected_plug2 = None
        self.Refresh()
        
    def OnLeftDown(self, event):
        x, y = event.GetPosition()
        self.selected_node = None
        
        if self.selected_plug:
            pass
        else:
            for key, r in self.nodeRects.items():
                if x>=r[0] and x<=r[0]+r[2] and y>=r[1] and y<=r[1]+r[3]:
                    self.selected_node = key
        
        self.left_down = True
        self.lastx, self.lasty = x, y
        self.Refresh()
        
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
        self.SetSizeHints(600,300,-1,-1)
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