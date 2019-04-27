import math
import numpy as np
import pickle
import pyrr
import random
import time
import wx

from utils import ortho, perspective, translate, rotate
from wx import glcanvas

from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.arrays import vbo
from OpenGL.GL import shaders

from readobj import Obj3D

from shadergraph import NodeFactory, ShaderGraph
from shadergraph import Plug, ColorValue, FloatValue, StringValue, ListValue

UNIFORM_FUNCTION = [None, glUniform1f, glUniform2f, glUniform3f, glUniform4f]

PLUG_CIRCLE_RADIUS = 4
PLUG_CIRCLE_SIZE = PLUG_CIRCLE_RADIUS * 2

REALTIME = True
RENDER_BACKGROUND = True
RENDER_FOREGROUND = True

File3D = 'cube2.obj'

__author__ = 'Bhupendra Aole'
__version__ = '0.1.0'

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
        
class GraphWindow( wx.Panel ):
    def __init__(self, parent, graph):
        super().__init__(parent, wx.ID_ANY)
        
        self.graph = graph
        self.nodeRects = {}
        self.pluglocation = {}
        self.lastx = self.lasty = 0
        self.panx = self.pany = 0
        self.origMouseDownPosition = (0,0)
        self.selection_rect = wx.Rect() #[0,0,0,0]
        self.popupCoords = (0,0)
        
        self.hovered_node = None
        self.selected_nodes = []
        self.rect_selected_nodes = []
        self.selected_plug = None
        self.selected_plug2 = None
        
        self.BLACK_BRUSH = wx.Brush(wx.Colour(0,0,0))
        self.TGRAY_BRUSH_100 = wx.Brush(wx.Colour(100,100,100, 200))
        self.GRAY_BRUSH_200 = wx.Brush(wx.Colour(200,200,200))
        self.GRAY_BRUSH_250 = wx.Brush(wx.Colour(250,250,250))
        self.GRAY_BRUSH_100 = wx.Brush(wx.Colour(100,100,100))
        self.BLACK_BRUSH_100 = wx.Brush(wx.Colour(0,0,0,100))
        self.RED_BRUSH = wx.Brush(wx.Colour(255,0,0))
        self.ERROR_BRUSH = wx.Brush(wx.Colour(200,100,100))
        
        self.BLACK_PEN = wx.Pen(wx.Colour(0,0,0))
        self.SELECTION_PEN = wx.Pen(wx.Colour(0,0,0,150), style=wx.PENSTYLE_LONG_DASH)
        self.GRAY_PEN_100 = wx.Pen(wx.Colour(100,100,100))
        self.GRAY_PEN_150 = wx.Pen(wx.Colour(150,150,150))
        self.GRAY_PEN_200 = wx.Pen(wx.Colour(200,200,200))
        self.RED_PEN = wx.Pen(wx.Colour(255,0,0))
        self.ERROR_PEN = wx.Pen(wx.Colour(200,100,100),10)
        
        self.PLUGVALUEGAP = 6
        self.TXT4WIDTH, self.TXTHEIGHT = 0,0
        
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        
        self.InitUI()

    def InitUI(self):
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
        self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleDown)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
        self.Bind(wx.EVT_SIZE, self.OnSize)

        self.font = self.GetFont()
        
        self.listbox = wx.ListCtrl(self, size=(100,-1), style=wx.LC_REPORT|wx.LC_NO_HEADER|wx.LC_SINGLE_SEL|wx.LC_HRULES)
        self.hideListBox()
        self.listbox.AppendColumn('Available')
        self.listbox.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnListItemSelected)
        
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
        
        gc = wx.GraphicsContext.Create(dc)
        gc.SetFont(self.font, wx.Colour(0,0,0))
        
        # paint background
        w, h = gc.GetSize()
        w, h = int(w), int(h)
        
        gridsize = 50
        # draw border
        if self.graph.in_error:
            gc.SetPen(self.ERROR_PEN)
            
        gc.SetBrush(self.GRAY_BRUSH_200)
        gc.DrawRectangle(0,0,w,h)
        
        # draw secondary axis lines
        gc.SetPen(self.GRAY_PEN_150)
        for x in range(int(w/2+self.panx)%gridsize,w-1,gridsize):
            gc.StrokeLine(x, 0, x, h)
        for y in range(int(h/2+self.pany)%gridsize,h-1,gridsize):
            gc.StrokeLine(0, y, w, y)
        # draw main axis lines (horizontal and vertical)
        gc.SetPen(self.GRAY_PEN_100)
        gc.StrokeLine(0, h/2+self.pany, w, h/2+self.pany)
        gc.StrokeLine(w/2+self.panx, 0, w/2+self.panx, h)
        
        self.TXT4WIDTH, self.TXTHEIGHT = gc.GetTextExtent('TEXT')
        
        if self.graph:
            # reversed for correctly mouse picking top (z order) node.
            for node in reversed(self.graph.nodes):
                locx, locy = node.location[0]+self.panx, node.location[1]+self.pany
                gc.SetPen(self.BLACK_PEN)
                gc.SetBrush(wx.NullBrush)
                
                # get max name length
                nodename = node.name
                txtwidth, txtheight = gc.GetTextExtent(nodename)
                
                plugcount = 0
                for key, plug in {**node.outplugs, **node.inplugs}.items():
                    if not plug.display:
                        continue
                        
                    plugcount += 1
                    name = str(key)
                    w, h = gc.GetTextExtent(name)
                    if w > txtwidth:
                        txtwidth = w
                
                bodyh = plugcount * (txtheight+4)
                # draw Selection indication
                if node in self.selected_nodes+self.rect_selected_nodes:
                    gc.SetPen(wx.NullPen)
                    gc.SetBrush(self.TGRAY_BRUSH_100)
                    gc.DrawRoundedRectangle(locx-3, locy-3, txtwidth+4+15+7, txtheight+4+bodyh+7, 3)
                    
                gc.SetPen(self.BLACK_PEN)
                # print name
                gc.SetBrush(self.GRAY_BRUSH_250)
                gc.DrawRoundedRectangle(locx, locy, txtwidth+4+15, txtheight+4, 3)
                
                gc.DrawText(nodename, locx+2, locy+2)
                if node.can_delete:
                    gc.DrawText('X', locx+txtwidth+4+6, locy+2)
            
                # print body
                gc.DrawRoundedRectangle(locx, locy+txtheight+4, txtwidth+4+15, bodyh, 3)

                #if node not in self.nodeRects:
                self.nodeRects[node] = wx.Rect(locx, locy, txtwidth+4+15, txtheight+4+bodyh)
                
                y = locy+txtheight+4
                # out plugs
                for key, plug in node.outplugs.items():
                    if not plug.display:
                        continue
                        
                    y += 2
                    name = str(key)
                    w, h = gc.GetTextExtent(name)
                    
                    gc.SetPen(self.BLACK_PEN)
                    gc.DrawText(name, locx+2 + (txtwidth+11-w), y)
                    
                    if not plug.internal:
                        if plug==self.selected_plug or plug==self.selected_plug2:
                            gc.SetPen(self.RED_PEN)
                            
                        gc.DrawEllipse(locx+2+txtwidth+6+10-PLUG_CIRCLE_RADIUS, y+h/2-PLUG_CIRCLE_RADIUS, PLUG_CIRCLE_SIZE,PLUG_CIRCLE_SIZE)
                        self.pluglocation[plug] = (locx+2+txtwidth+6+10, y+h/2)
                    y += txtheight
                    
                # in plugs
                for key, plug in node.inplugs.items():
                    if not plug.display:
                        continue
                        
                    y += 2
                    name = str(key)
                    w, h = gc.GetTextExtent(name)
                    
                    gc.SetPen(self.BLACK_PEN)
                    # draw plug inputs
                    if isinstance(plug.value, ColorValue):
                        COLOR_BRUSH = wx.Brush(wx.Colour(*plug.value.GetColorInt()))
                        gc.SetBrush(COLOR_BRUSH)
                        gc.DrawRoundedRectangle(locx+self.PLUGVALUEGAP, y, self.TXT4WIDTH, self.TXTHEIGHT, 3)
                        gc.SetBrush(wx.NullBrush)
                    elif isinstance(plug.value, FloatValue):
                        gc.DrawRectangle(locx+self.PLUGVALUEGAP, y, self.TXT4WIDTH, self.TXTHEIGHT)
                        gc.DrawText(plug.value.GetFloat(), locx+self.PLUGVALUEGAP+3, y)
                    elif isinstance(plug.value, StringValue):
                        gc.DrawRectangle(locx+self.PLUGVALUEGAP, y, self.TXT4WIDTH*2, self.TXTHEIGHT)
                        gc.DrawText(plug.value.value, locx+self.PLUGVALUEGAP+3, y)
                    elif isinstance(plug.value, ListValue):
                        gc.DrawRectangle(locx+self.PLUGVALUEGAP, y, self.TXT4WIDTH*2, self.TXTHEIGHT)
                        gc.DrawText(plug.value.value, locx+self.PLUGVALUEGAP+3, y)
                    else:
                        gc.DrawText(name, locx+self.PLUGVALUEGAP, y)
                    
                    if not plug.internal:
                        gc.SetBrush(self.GRAY_BRUSH_250)
                        # draw plug circle
                        if plug==self.selected_plug or plug==self.selected_plug2:
                            gc.SetPen(self.RED_PEN)
                       
                        gc.DrawEllipse(locx-PLUG_CIRCLE_RADIUS, y+h/2-PLUG_CIRCLE_RADIUS, PLUG_CIRCLE_SIZE,PLUG_CIRCLE_SIZE)
                        
                    self.pluglocation[plug] = (locx, y+h/2)
                        
                    y += txtheight
                    
            # draw connections
            gc.SetPen(self.BLACK_PEN)
            for node in self.graph.nodes:
                for plug in node.inplugs.values():
                    if not plug.display or plug.internal:
                        continue
                        
                    x1, y1 = self.pluglocation[plug]
                    if isinstance(plug, Plug) and plug.value.parent and plug.value.parent!= node:
                        path = gc.CreatePath()
                        x2, y2 = self.pluglocation[plug.value]
                        path.MoveToPoint(x1, y1)
                        ctx = min(50, math.sqrt((x1-x2)**2+(y1-y2)**2))
                        path.AddCurveToPoint(x1-ctx, y1, x2+ctx, y2, x2, y2)
                        gc.StrokePath(path)
                        
                        gc.SetBrush(self.BLACK_BRUSH)
                        if plug == self.selected_plug or plug == self.selected_plug2:
                            gc.SetBrush(self.RED_BRUSH)
                        gc.DrawEllipse(x1-PLUG_CIRCLE_RADIUS, y1-PLUG_CIRCLE_RADIUS, PLUG_CIRCLE_SIZE,PLUG_CIRCLE_SIZE)
                        
                        gc.SetBrush(self.BLACK_BRUSH)
                        if plug.value == self.selected_plug or plug.value == self.selected_plug2:
                            gc.SetBrush(self.RED_BRUSH)
                        gc.DrawEllipse(x2-PLUG_CIRCLE_RADIUS, y2-PLUG_CIRCLE_RADIUS, PLUG_CIRCLE_SIZE,PLUG_CIRCLE_SIZE)
                        
            # hovered plug
            if self.selected_plug and wx.GetMouseState().LeftIsDown():
                x1, y1 = self.pluglocation[self.selected_plug]
                x2, y2 = self.ScreenToClient(wx.GetMousePosition())
                
                if abs(x1-x2)>PLUG_CIRCLE_RADIUS or abs(y1-y2)>PLUG_CIRCLE_RADIUS:
                    if self.selected_plug.inParam:
                        x1, x2 = x2, x1
                        y1, y2 = y2, y1
                        
                    path = gc.CreatePath()
                    path.MoveToPoint(x1, y1)
                    ctx = min(50, math.sqrt((x1-x2)**2+(y1-y2)**2))
                    path.AddCurveToPoint(x1+ctx, y1, x2-ctx, y2, x2, y2)
                    gc.StrokePath(path)
        
            # selection rect
            if self.selection_rect.width>0 and self.selection_rect.height>0:
                x,y,w,h = self.selection_rect
                gc.SetPen(self.SELECTION_PEN)
                gc.SetBrush(wx.NullBrush)
                gc.DrawRectangle(x, y, w, h)
                
    def OnAddNode(self, event):
        node = NodeFactory.getNewNode(event.GetEventObject().GetLabelText(event.GetId()))
        node.location = self.popupCoords
        self.selected_nodes = [node]
        self.graph.nodes.append(node)
        self.graph.requires_compilation = True
        self.Refresh()
        
    def OnSize(self, e):
        self.Refresh()

    def OnMiddleDown(self, event):
        self.hideListBox()
        
    def OnRightDown(self, event):
        self.selected_nodes.clear()
        self.hideListBox()
        if self.hovered_node:
            self.selected_nodes = [self.hovered_node]
            
        self.popupCoords = event.GetPosition() - (self.panx, self.pany)
        self.PopupMenu( self.popupMenu, event.GetPosition() )

    def OnMouseMotion(self, event):
        x, y = event.GetPosition()
        dx, dy = x-self.lastx, y-self.lasty
        self.lastx, self.lasty = x, y
        
        if event.Dragging():
            if event.MiddleIsDown():
                self.panx += dx
                self.pany += dy
            elif event.LeftIsDown():
                if self.selected_plug: # find 2nd plug
                    self.selected_plug2 = None
                    for plug, loc in self.pluglocation.items():
                        lx, ly = loc
                        if x>=lx-PLUG_CIRCLE_RADIUS and x<=lx+PLUG_CIRCLE_RADIUS and y>=ly-PLUG_CIRCLE_RADIUS and y<=ly+PLUG_CIRCLE_RADIUS:
                            if self.selected_plug != plug:
                                self.selected_plug2 = plug
                            break
                elif self.selected_nodes and self.hovered_node and (not self.selection_rect.width>0 or not self.selection_rect.height>0): # move node
                    for node in self.selected_nodes:
                        node.location[0] += dx
                        node.location[1] += dy
                else: # selection rect
                    x1, y1 = x, y
                    x2, y2 = self.origMouseDownPosition
                    if x2<x1:
                        x1,x2=x2,x1
                    if y2<y1:
                        y1,y2=y2,y1
                    self.selection_rect = wx.Rect(x1,y1,x2-x1,y2-y1)
                    
                    self.rect_selected_nodes.clear()
                    if not wx.GetKeyState(wx.WXK_SHIFT):
                        self.selected_nodes.clear()
                    for node, rect in self.nodeRects.items():
                        if rect.Intersects(self.selection_rect):
                            if node not in self.rect_selected_nodes:
                                self.rect_selected_nodes.append(node)
                    
        else: # find node/ 1st plug
            self.hovered_node = None
            self.selected_plug = None
            self.selected_plug2 = None
            found = False
            for plug, loc in self.pluglocation.items():
                lx, ly = loc
                if x>=lx-PLUG_CIRCLE_RADIUS and x<=lx+PLUG_CIRCLE_RADIUS and y>=ly-PLUG_CIRCLE_RADIUS and y<=ly+PLUG_CIRCLE_RADIUS:
                    self.selected_plug = plug
                    found = True
                    break
            if not found: # if no plug found
                for node, rect in self.nodeRects.items():
                    if rect.Contains(x,y):
                        self.hovered_node = node
                        break
        self.Refresh()
        
    def hideListBox( self ):
        self.listbox.Show(False)
        self.SetFocusIgnoringChildren()
        
    def OnListItemSelected( self, event ):
        currentItem = self.listbox.GetFirstSelected()
        self.hideListBox()
        plug = self.listbox.plug
        if plug:
            value = plug.getList()[currentItem]
            plug.value.SetValue(value)
            self.graph.requires_compilation = True
        
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
        elif isinstance(plug.value, StringValue):
            dialog = wx.TextEntryDialog(self, 'Enter Value', caption='Enter Value',value=plug.value.GetValue())
            if dialog.ShowModal() == wx.ID_OK:
                plug.value.SetValue(dialog.GetValue())
                self.graph.requires_compilation = True
        elif isinstance(plug.value, ListValue):
            self.listbox.DeleteAllItems()
            listitems = plug.getList()
            if listitems:
                setattr(self.listbox, 'plug', plug)
                x, y = self.pluglocation[plug]
                tosel = 0
                for idx, li in enumerate(listitems):
                    if li == plug.value.value:
                        tosel=idx
                    self.listbox.InsertItem(idx, li)
                self.listbox.Select(tosel)
                self.listbox.Focus(tosel)
                self.listbox.SetPosition((x+self.PLUGVALUEGAP+1,y-self.TXTHEIGHT/2+1))
                #self.listbox.SetSize((self.TXT4WIDTH*3, 200))
                self.listbox.SetColumnWidth(0, -1)
                self.listbox.Show(True)
            
    def OnLeftUp(self, event):
        x, y = event.GetPosition()
        self.selection_rect = wx.Rect()
        
        for node in self.rect_selected_nodes:
            if node not in self.selected_nodes:
                self.selected_nodes.append(node)
        self.rect_selected_nodes.clear()
        
        if self.selected_plug and self.selected_plug2:
            pin = self.selected_plug
            pout = self.selected_plug2
            if pin not in pin.parent.inplugs.values():
                pin, pout = pout, pin
            if pin in pin.parent.inplugs.values() and pout in pout.parent.outplugs.values():
                pin.setValue(pout)
                self.graph.requires_compilation = True
            
        # activate plug input
        if not self.selected_plug and self.hovered_node:
            for plug, loc in self.pluglocation.items():
                if plug.parent != self.hovered_node:
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
                    
        self.selected_plug = self.selected_plug2 = self.hovered_node = None
        self.Refresh()
        
    def OnLeftDown(self, event):
        x, y = event.GetPosition()
        self.origMouseDownPosition = event.GetPosition()
        
        self.hideListBox()
        shiftdown = wx.GetKeyState(wx.WXK_SHIFT)
        ctrldown = wx.GetKeyState(wx.WXK_CONTROL)
        
        # Clear all selection except with click on an existing selection
        if not shiftdown and not self.hovered_node in self.selected_nodes:
            self.selected_nodes.clear()
            
        if self.hovered_node:
            if self.hovered_node not in self.selected_nodes:
                self.selected_nodes.append(self.hovered_node)
            if not self.selected_plug:
                rect = self.nodeRects[self.hovered_node]
                # check if X is clicked
                if self.hovered_node.can_delete and x>(rect.x+rect.width)-20 and y<rect.y+20:
                    self.removeNode(self.hovered_node)
        
        elif self.selected_plug and ctrldown and self.selected_plug.inParam:
            self.selected_plug.setDefaultValue()
            self.graph.requires_compilation = True
        elif self.selected_plug:
            self.selected_nodes = [self.selected_plug.parent]
            
        self.lastx, self.lasty = x, y
        self.Refresh()
    
    def OnKeyDown(self, event):
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_DELETE:
            self.deleteSelectedNode()
        
    def deleteSelectedNode(self):
        for node in self.selected_nodes:
            self.removeNode(node)
            
    def removeNode(self, node):
        if not node.can_delete:
            return
            
        self.graph.removeNode(node)
        del self.nodeRects[node]
        self.hovered_node = None
        self.selected_nodes = []
        self.selected_plug = self.selected_plug2 = None
        self.graph.requires_compilation = True
        self.Refresh()
        
class Window( wx.Frame ):
    def __init__( self, *args, **kwargs ):
        super().__init__( *args, **kwargs )
        
        self.graph = ShaderGraph()
        
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
        
        # Tabs
        tabs = wx.Notebook( backPanel )
        tabs.Bind( wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnTabChanged )
        
        # GRAPH PANEL
        self.graphPanel = GraphWindow( tabs, self.glwindow.GetGraph() )
        tabs.InsertPage( 0, self.graphPanel, 'Shader Graph' )
        
        # CODE PANEL
        self.codePanel = wx.TextCtrl( tabs, style=wx.TE_MULTILINE )
        self.codePanel.SetEditable( False )
        tabs.InsertPage( 1, self.codePanel, 'Shader Code' )
        
        # LAYOUT
        gridSizer = wx.GridSizer(rows=1, cols=2, hgap=5, vgap=5)
        gridSizer.Add(tabs, 0, wx.EXPAND)
        gridSizer.Add(self.glwindow, 0, wx.EXPAND)
        
        backPanel.SetSizer(gridSizer)
        
        # MIN SIZE to avoid GL error
        self.SetSizeHints(200,100,-1,-1)
        
        # SHOW
        self.Show()
    
    def OnTabChanged( self, event ):
        vs, fs = self.glwindow.generateCode()
        code = '# Vertex Shader ...\n\n'+vs+'\n\n# Fragment Shader ...\n\n'+fs
        self.codePanel.SetValue(code)
        
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
                    self.OnTabChanged(None)
                    self.graph.updateVariableCount()
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
