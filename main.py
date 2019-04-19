import wx
import numpy as np
import time
import random
import pickle

from wx import glcanvas

from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.arrays import vbo
from OpenGL.GL import shaders

from readobj import Obj3D

from shadergraph import NodeFactory, FragmentShaderGraph
from shadergraph import Plug, ColorValue, FloatValue

UNIFORM_FUNCTION = [None, glUniform1f, glUniform2f, glUniform3f, glUniform4f]

REALTIME = True

__author__ = 'Bhupendra Aole'
__version__ = '0.1.0'

vertexShader = """
    #version 120
    
    void main() {
        gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
    }
    """

fragmentBGShader = """
    #version 330
    
    void main() {
        vec2 d = gl_FragCoord.xy/30;
        if(mod(int(d.x),2)==mod(int(d.y),2)) {
            gl_FragColor = vec4( .7, .7, .7, 1 );
        }
        else {
            gl_FragColor = vec4( .3, .3, .3, 1 );
        }
    }
    """

custom_nodes = {'sg_ScreenSize':('Screen Size', [('Width', 'float', 'sg_ScreenSize.x'), ('Height', 'float', 'sg_ScreenSize.y')], 'vec2','self.GetGLExtents()', glUniform2f)}

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

        width, height = self.GetGLExtents()
        self.OnReshape( width, height )
        #self.Refresh( False )
        event.Skip()

    def processPaintEvent(self, event):
        #self.SetCurrent( self.context )

        # This is a 'perfect' time to initialize OpenGL ... only if we need to
        if not self.GLinitialized:
            self.OnInitGL()
            self.GLinitialized = True

        if self.graph.requires_compilation:
            self.compileShaders()
            
        self.OnDraw()
        event.Skip()

    #
    # GLFrame OpenGL Event Handlers

    def OnInitGL(self):
        """Initialize OpenGL for use in the window."""
        glClearColor(1, 1, 1, 1)

        # setup transparency
        glDisable(GL_CULL_FACE)
        glEnable(GL_BLEND);
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
        
        width, height = self.GetGLExtents()
        bgdata = [[width,height,0.],  [0.,height,0.],  [width,0.,0.],  [0.,0.,0.]]
        self.bgvbo = vbo.VBO( np.array( bgdata, 'f' ) )
        
        self.compileBGShaders()
        
        cube = Obj3D( 'cube.obj' )
        fgdata = cube.getVerticesFlat()
        self.fgvbo = vbo.VBO( np.array( fgdata, 'f' ) )
        
        self.compileShaders()
        
        if REALTIME:
            self.timer.Start(1000/60)    # 1 second interval
        
    def compileBGShaders(self):
        VERTEX_SHADER = shaders.compileShader( vertexShader, GL_VERTEX_SHADER )
        FRAGMENT_SHADER = shaders.compileShader( fragmentBGShader, GL_FRAGMENT_SHADER )
        
        self.bgshader = shaders.compileProgram( VERTEX_SHADER, FRAGMENT_SHADER )
    
    def compileShaders(self):
        VERTEX_SHADER = shaders.compileShader( vertexShader, GL_VERTEX_SHADER )
        
        # Fragment Shader
        code = ""
        globalcode = ""
        self.graph.prepare()
        code, globalcode = self.graph.nodes[0].generateCode('gl_FragColor', code, globalcode)
        
        fragmentShader = "#version 330\n\n"
        
        fragmentShader += globalcode
        
        for name, value in custom_nodes.items():
            fragmentShader += 'uniform '+value[2]+' '+name+';\n' #' = '+value[3](self)+';\n'
            
        fragmentShader += "\nvoid main() {\n"
        fragmentShader += code
        fragmentShader += "}"
        
        print('====================')
        print(fragmentShader)
        print('====================')
        FRAGMENT_SHADER = shaders.compileShader( fragmentShader, GL_FRAGMENT_SHADER )
        
        self.shader = shaders.compileProgram( VERTEX_SHADER, FRAGMENT_SHADER )

        self.graph.requires_compilation = False
        
    def OnReshape( self, width, height ):
        """Reshape the OpenGL viewport based on the dimensions of the window."""
        glViewport( 0, 0, width, height )
        
        if self.GLinitialized:
            bgdata = [[width,height,0.],  [0.,height,0.],  [width,0.,0.],  [0.,0.,0.]]
            if self.bgvbo:
                self.bgvbo.delete()
            self.bgvbo = vbo.VBO( np.array( bgdata, 'f' ) )
        
    def OnDraw( self ):
        glClear( GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT )

        width, height = self.GetGLExtents()
        
        # draw background
        glMatrixMode( GL_PROJECTION )
        glLoadIdentity()
        glOrtho( 0,width, 0, height, -1, 1 )
        
        glMatrixMode(GL_MODELVIEW);
        glLoadIdentity()
        
        glPushMatrix()
        
        shaders.glUseProgram( self.bgshader )
        
        self.bgvbo.bind()
        glEnableClientState( GL_VERTEX_ARRAY );
        glVertexPointerf( self.bgvbo )
        
        glDrawArrays( GL_TRIANGLE_STRIP, 0, len( self.bgvbo ) )
        
        self.bgvbo.unbind()
        glDisableClientState( GL_VERTEX_ARRAY );
        
        glPopMatrix()
        
        # draw foreground
        glMatrixMode( GL_PROJECTION )
        glLoadIdentity()
        gluPerspective( 45.0, width/height, self.near_plane, self.far_plane )

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        glPushMatrix()
        glTranslate( self.world_pos[0], self.world_pos[1], self.world_pos[2] )
        glRotated( self.world_rot[1], 0, 1, 0 )
        glRotated( self.world_rot[0], 1, 0, 0 )
        
        shaders.glUseProgram( self.shader )
        
        self.fgvbo.bind()
        glEnableClientState( GL_VERTEX_ARRAY );
        glVertexPointerf( self.fgvbo )
        
        for uname, ucount, ufuncs in self.graph.uniforms.values():
            UNIFORM_FUNCTION[ucount]( glGetUniformLocation(self.shader, uname), *ufuncs() )
        
        for name, value in custom_nodes.items():
            value[4]( glGetUniformLocation(self.shader, name), *eval(value[3]) )
            
        glDrawArrays( GL_TRIANGLES, 0, len( self.fgvbo ) )
        self.fgvbo.unbind()
        glDisableClientState( GL_VERTEX_ARRAY );
        shaders.glUseProgram( 0 )
        
        glPopMatrix()
        
        self.SwapBuffers()
        
class GraphWindow( wx.Panel ):
    def __init__(self, parent, graph):
        super().__init__(parent, wx.ID_ANY)
        
        self.graph = graph
        self.nodeRects = {}
        self.pluglocation = {}
        self.left_down = False
        self.middle_down = False
        self.selected_node = None
        self.selected_plug = None
        self.selected_plug2 = None
        self.lastx = self.lasty = 0
        self.panx = self.pany = 0
        self.popupCoords = (0,0)
        
        self.BLACK_BRUSH = wx.Brush(wx.Colour(0,0,0))
        self.BLACK_BRUSH_100 = wx.Brush(wx.Colour(0,0,0,100))
        self.RED_BRUSH = wx.Brush(wx.Colour(255,0,0))
        self.BLACK_PEN = wx.Pen(wx.Colour(0,0,0))
        self.GRAY_PEN_100 = wx.Pen(wx.Colour(100,100,100))
        self.GRAY_PEN_200 = wx.Pen(wx.Colour(200,200,200))
        self.RED_PEN = wx.Pen(wx.Colour(255,0,0))
        
        self.PLUGVALUEGAP = 6
        self.TXT4WIDTH, self.TXTHEIGHT = 0,0
        
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        
        # custom nodes
        for value in custom_nodes.values():
            NodeFactory.addCustomNode(value[0], value[1])
            
        self.InitUI()

    def InitUI(self):
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleDown)
        self.Bind(wx.EVT_MIDDLE_UP, self.OnMiddleUp)
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)

        #POPUP MENU
        self.popupMenu = wx.Menu()
        for idx, nodename in enumerate(NodeFactory.getNodeNames()):
            pm = self.popupMenu.Append( idx, f'{nodename}', 'Add '+nodename )
            self.Bind( wx.EVT_MENU, self.OnAddNode, pm )
        
    def SetGraph(self, graph):
        self.graph = graph
        self.Refresh()
        
    def OnEraseBackground(self, event):
        pass
        
    def OnPaint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.Clear()
        
        # paint background
        w, h = dc.GetSize().Get()
        gridsize = 50
        # draw border
        dc.DrawRectangle(0,0,w,h)
        # draw secondary axis lines
        dc.SetPen(self.GRAY_PEN_200)
        for x in range(int(w/2+self.panx)%gridsize,w-1,gridsize):
            dc.DrawLine(x, 0, x, h)
        for y in range(int(h/2+self.pany)%gridsize,h-1,gridsize):
            dc.DrawLine(0, y, w, y)
        # draw main axis lines (horizontal and vertical)
        dc.SetPen(self.GRAY_PEN_100)
        dc.DrawLine(0, h/2+self.pany, w, h/2+self.pany)
        dc.DrawLine(w/2+self.panx, 0, w/2+self.panx, h)
        
        self.TXT4WIDTH, self.TXTHEIGHT = dc.GetTextExtent('TEXT')
        
        if self.graph:
            for node in self.graph.nodes:
                locx, locy = node.location[0]+self.panx, node.location[1]+self.pany
                dc.SetPen(self.BLACK_PEN)
                dc.SetBrush(wx.NullBrush)
                
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
                if node.can_delete:
                    dc.DrawText('X', locx+txtwidth+4+6, locy+2)
            
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
                    
                    dc.SetPen(self.BLACK_PEN)
                    # draw plug inputs
                    if isinstance(plug.value, ColorValue):
                        COLOR_BRUSH = wx.Brush(wx.Colour(*plug.value.GetColorInt()))
                        dc.SetBrush(COLOR_BRUSH)
                        dc.DrawRoundedRectangle(locx+2+txtwidth+10-self.TXT4WIDTH, y, self.TXT4WIDTH, self.TXTHEIGHT, 3)
                        dc.SetBrush(wx.NullBrush)
                    elif isinstance(plug.value, FloatValue):
                        dc.DrawRectangle(locx+2+txtwidth+10-self.TXT4WIDTH, y, self.TXT4WIDTH, self.TXTHEIGHT)
                        dc.DrawText(plug.value.GetFloat(), locx+2+txtwidth+13-self.TXT4WIDTH, y)
                    else:
                        dc.DrawText(name, locx+2 + (txtwidth+11-w), y)
                    
                    if plug==self.selected_plug or plug==self.selected_plug2:
                        dc.SetPen(self.RED_PEN)
                        
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
                    
                    dc.SetPen(self.BLACK_PEN)
                    # draw plug inputs
                    if isinstance(plug.value, ColorValue):
                        COLOR_BRUSH = wx.Brush(wx.Colour(*plug.value.GetColorInt()))
                        dc.SetBrush(COLOR_BRUSH)
                        dc.DrawRoundedRectangle(locx+self.PLUGVALUEGAP, y, self.TXT4WIDTH, self.TXTHEIGHT, 3)
                        dc.SetBrush(wx.NullBrush)
                    elif isinstance(plug.value, FloatValue):
                        dc.DrawRectangle(locx+self.PLUGVALUEGAP, y, self.TXT4WIDTH, self.TXTHEIGHT)
                        dc.DrawText(plug.value.GetFloat(), locx+self.PLUGVALUEGAP+3, y)
                    else:
                        dc.DrawText(name, locx+self.PLUGVALUEGAP, y)
                    
                    # draw plug circle
                    if plug==self.selected_plug or plug==self.selected_plug2:
                        dc.SetPen(self.RED_PEN)
                   
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
                
    def OnAddNode(self, event):
        node = NodeFactory.getNewNode(event.GetEventObject().GetLabelText(event.GetId()))
        node.location = self.popupCoords
        self.graph.nodes.append(node)
        self.graph.requires_compilation = True
        
    def OnSize(self, e):
        self.Refresh()

    def OnMiddleDown(self, event):
        self.middle_down = True
        
    def OnMiddleUp(self, event):
        self.middle_down = False
        
    def OnRightDown(self, event):
        self.popupCoords = event.GetPosition() - (self.panx, self.pany)
        self.PopupMenu( self.popupMenu, event.GetPosition() )

    def OnMouseMotion(self, event):
        x, y = event.GetPosition()
        dx, dy = x-self.lastx, y-self.lasty
        if self.middle_down:
            self.panx += dx
            self.pany += dy
        else:
            if not self.selected_plug:
                self.selected_node = None
                for node, r in self.nodeRects.items():
                    if x>=r[0] and x<=r[0]+r[2] and y>=r[1] and y<=r[1]+r[3]:
                        self.selected_node = node
                        
            self.selected_plug2 = None
            found = False
            for plug, loc in self.pluglocation.items():
                lx, ly = loc
                if x>=lx-3 and x<=lx+3 and y>=ly-3 and y<=ly+3:
                    if self.left_down and self.selected_plug and self.selected_plug != plug:
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
        
    def triggerPlugInput( self, plug ):
        if not plug.editable:
            return
            
        if isinstance(plug.value, ColorValue):
            data = wx.ColourData()
            data.SetColour(wx.Colour(*plug.value.GetColorInt()))
            dialog = wx.ColourDialog(self, data)
            if dialog.ShowModal() == wx.ID_OK:
                retColor = dialog.GetColourData().GetColour()
                plug.value.SetColorInt(*retColor.Get(False))
                self.graph.requires_compilation = True
        elif isinstance(plug.value, FloatValue):
            dialog = wx.TextEntryDialog(self, 'Enter Value', caption='Enter Value',value=plug.value.GetFloat())
            if dialog.ShowModal() == wx.ID_OK:
                plug.value.SetFloat(dialog.GetValue())
                self.graph.requires_compilation = True
    
    def OnLeftUp(self, event):
        self.left_down = False
        x, y = event.GetPosition()
        
        if self.selected_plug and self.selected_plug2:
            pin = self.selected_plug
            pout = self.selected_plug2
            if pin not in pin.parent.inplugs.values():
                pin, pout = pout, pin
            if pin in pin.parent.inplugs.values() and pout in pout.parent.outplugs.values():
                pin.setValue(pout)
                self.graph.requires_compilation = True
            
        # activate plug input
        if not self.selected_plug and self.selected_node:
            for plug, loc in self.pluglocation.items():
                if plug.parent != self.selected_node:
                    continue
                lx, ly = loc
                # input plugs on the left side
                if plug.inParam and x>=lx+self.PLUGVALUEGAP and x<=lx+self.PLUGVALUEGAP+self.TXT4WIDTH and y>=ly-self.TXTHEIGHT/2 and y<=ly+self.TXTHEIGHT/2:
                    self.triggerPlugInput(plug)
                    break
                # output plugs on the right side
                elif not plug.inParam and x>lx-(self.PLUGVALUEGAP+self.TXT4WIDTH) and x<lx-self.PLUGVALUEGAP and y>=ly-self.TXTHEIGHT/2 and y<=ly+self.TXTHEIGHT/2:
                    self.triggerPlugInput(plug)
                    break
                    
        self.selected_plug = self.selected_plug2 = self.selected_node = None
        self.Refresh()
        
    def OnLeftDown(self, event):
        x, y = event.GetPosition()
        
        self.selected_node = None
        if not self.selected_plug:
            for node, r in self.nodeRects.items():
                if x>=r[0] and x<=r[0]+r[2] and y>=r[1] and y<=r[1]+r[3]:
                    # check if X is clicked
                    if node.can_delete and x>r[0]+r[2]-10 and y<r[1]+10:
                        self.removeNode(node)
                        break
                    else:
                        self.selected_node = node
        elif self.selected_plug and wx.GetKeyState(wx.WXK_CONTROL) and self.selected_plug.inParam:
            self.selected_plug.setDefaultValue()
            self.graph.requires_compilation = True
            
        self.left_down = True
        self.lastx, self.lasty = x, y
        self.Refresh()
        
    def removeNode(self, node):
        self.graph.removeNode(node)
        del self.nodeRects[node]
        self.selected_node = None
        self.selected_plug = self.selected_plug2 = None
        self.graph.requires_compilation = True
        
class Window( wx.Frame ):
    def __init__( self, *args, **kwargs ):
        super().__init__( *args, **kwargs )
        
        self.graph = FragmentShaderGraph()
        
        self.initUI()
    
    def initUI( self ):
        # MENU
        fmenu = wx.Menu()
        
        fitem = fmenu.Append( wx.ID_NEW, '&New\tCtrl+N', 'New file' )
        self.Bind( wx.EVT_MENU, self.OnNew, fitem )
        
        fitem = fmenu.Append( wx.ID_OPEN, '&Open\tCtrl+O', 'Open file' )
        self.Bind( wx.EVT_MENU, self.OnOpen, fitem )
        
        fitem = fmenu.Append( wx.ID_SAVEAS, 'Save &As', 'Save file as' )
        self.Bind( wx.EVT_MENU, self.OnSaveAs, fitem )
        
        fmenu.AppendSeparator()
        fitem = fmenu.Append( wx.ID_EXIT, 'E&xit\tCtrl+Q', 'Exit Application' )
        self.Bind(wx.EVT_MENU, self.OnQuit, fitem)
        
        mbar = wx.MenuBar()
        mbar.Append( fmenu, '&File' )
        
        self.SetMenuBar( mbar )
        
        # BACK PANEL
        backPanel = wx.Panel(self, wx.ID_ANY)
        
        # GL WINDOW
        self.glwindow = GLFrame( backPanel, self.graph)
        
        # GRAPH PANEL
        self.graphPanel = GraphWindow( backPanel, self.glwindow.GetGraph() )
        
        # LAYOUT
        gridSizer = wx.GridSizer(rows=1, cols=2, hgap=5, vgap=5)
        gridSizer.Add(self.graphPanel, 0, wx.EXPAND)
        gridSizer.Add(self.glwindow, 0, wx.EXPAND)
        
        backPanel.SetSizer(gridSizer)
        
        # MIN SIZE to avoid GL error
        self.SetSizeHints(200,100,-1,-1)
        
        # SHOW
        self.Show()
        
    def OnQuit( self, event ):
        self.Close()
    
    def OnNew( self, event ):
        self.graph.new()
        self.graph.requires_compilation = True
        
    def OnOpen( self, event ):
        with wx.FileDialog(self, "Save GL Shader Graph file", wildcard="GL Shader Graph files (*.glsg)|*.glsg",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:

            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return     # the user changed their mind

            # Proceed loading the file chosen by the user
            pathname = fileDialog.GetPath()
            try:
                with open(pathname, 'rb') as f:
                    self.graph = pickle.load(f)
                    self.glwindow.SetGraph(self.graph)
                    self.graphPanel.SetGraph(self.graph)
            except IOError:
                wx.LogError("Cannot open file '%s'." % newfile)
            
    def OnSaveAs( self, event ):
        with wx.FileDialog(self, "Save GL Shader Graph file", wildcard="GL Shader Graph files (*.glsg)|*.glsg",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:

            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return     # the user changed their mind

            # save the current contents in the file
            pathname = fileDialog.GetPath()
            try:
                with open(pathname, 'wb') as f:
                    pickle.dump(self.graph, f, 0)
            except IOError:
                wx.LogError("Cannot save current data in file '%s'." % pathname)
        
class Application( wx.App ):
    def run( self ):
        frame = Window(None, wx.ID_ANY, 'OpenGL Shader Graph', size=(1000,450))
        frame.Show()

        self.MainLoop()
        self.Destroy()
        
Application().run()
