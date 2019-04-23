import random

class Plug:
    count = 1
    def __init__(self, name, parent, type, variable, value, generate_variable=True, display=True, inParam=True, declare_variable=True, internal = False):
        self.name = name
        self.parent = parent
        self.type = type
        self.variable = variable
        self.value = value
        self.defaultValue = value
        self.inParam = inParam
        self.declared = False
        self.declare_variable = declare_variable
        self.editable = True
        self.internal = internal
        
        if generate_variable:
            self.variable += str(Plug.count)
            Plug.count += 1
        
        self.display = display
        
    def __str__(self):
        if isinstance(self.value, Plug):
            return f'{self.type} {self.variable} = {self.value.variable}'
        else:
            return f'{self.type} {self.variable} = {self.value}'
        
    def setValue(self, value):
        self.value = value
        
    def setDefaultValue(self):
        self.value = self.defaultValue
        
class Value:
    def __init__(self, value=''):
        self.parent = None
        self.value = value
        
    def __str__(self):
        return f'{self.value}'
        
    def __repr__(self):
        return self.__str__()
    
    def GetValue(self):
        return self.value
    
    def SetValue(self, value):
        self.value = value
        
class ColorValue(Value):
    def __init__(self, color=(.9,.9,.9,1)):
        super().__init__()
        self.color = color
        
    def __str__(self):
        return f'vec4({self.color[0]}, {self.color[1]}, {self.color[2]}, {self.color[3]})'
    
    def GetColorInt(self):
        return (self.color[0]*255, self.color[1]*255, self.color[2]*255, self.color[3]*255)
    
    def SetColorInt(self, r, g, b):
        self.color = (round(r/255.0,3), round(g/255.0,3), round(b/255.0,3), 1.0)
        
class FloatValue(Value):
    def __init__(self, value=1):
        super().__init__(value)
        
    def GetFloat(self):
        return str(round(self.value, 3))
        
    def SetFloat(self, value):
        try:
            self.value = float(value)
        except:
            pass
        
class StringValue(Value):
    def __init__(self, value='sin'):
        super().__init__(value)

class Node:
    def __init__( self, name='Node' ):
        self.inplugs = {}
        self.outplugs = {}
        self.name = name
        self.active = True
        self.location = [0,0]
        self.can_delete = True
        
    def addInPlug(self, plug):
        plug.inParam = True
        self.inplugs[plug.name] = plug
        
    def addOutPlug(self, plug):
        plug.inParam = False
        if self.inplugs:
            plug.editable = False
        self.outplugs[plug.name] = plug
        
    def setValue(self, name, plug):
        self.inplugs[name].setValue(plug)
        
    def getInPlug(self, name):
        return self.inplugs[name]
        
    def getOutPlug(self, name):
        return self.outplugs[name]
        
    def __str__(self):
        return str(type(self))
        
    def getGlobalCode(self):
        return None
        
    def generateCode(self, name, code, globalcode):
        gc = self.getGlobalCode()
        if gc:
            globalcode += gc
            
        for plugname, plug in self.inplugs.items():
            if isinstance(plug.value, Plug) and plug.value.parent!=self:
                if isinstance(plug.value.parent, UniformNode):
                    if not plug.value.declared:
                        globalcode += plug.value.value + ";\n"
                        plug.value.declared = True
                else:
                    if plug.value.declare_variable and not plug.value.declared:
                        out, gc = plug.value.parent.generateCode(plug.value.name, code, globalcode)
                        code = out
                        globalcode = gc
                        plug.value.declared = True
            if plug.declare_variable:
                out = f'\t{plug};\n'
                code += out
        code += '\t'+self.customCode(name).strip()+';\n'
        
        return code, globalcode
        
    def customCode(self, name):
        return f'{self.outplugs[name]}'
        
class UniformNode(Node):
    varcount = 1
    def __init__(self, name, type, count, function):
        super().__init__(name)
        
        name = name+str(UniformNode.varcount)
        UniformNode.varcount += 1
        
        self.uniform = (name, count, function)
        
        self.plug = Plug('Uniform', self, type, name, "uniform "+type+" "+name, inParam=False, generate_variable=False)
        self.addOutPlug(self.plug)
        self.plug.editable = False
        
    def __str__(self):
        return self.plug.value
        
    def __repr__(self):
        return self.__str__()
        
class UniformRandomFloatNode(UniformNode):
    def __init__(self):
        super().__init__('RandomFloat', 'float', 1, UniformRandomFloatNode.getRandomFloat)
        
    def getRandomFloat():
        return [random.random()]
        
class UniformRandomColorNode(UniformNode):
    def __init__(self):
        super().__init__('RandomColor', 'vec4', 4, UniformRandomColorNode.getRandomColor)
        
    def getRandomColor():
        return (random.random(), random.random(), random.random(), 1)
        
class ScaleNode(Node):
    def __init__(self):
        super().__init__('Scale')
        
        self.addInPlug(Plug('ScaleFloat', self, 'float', 'scale', FloatValue()))
        self.addInPlug(Plug('ScaleInColor', self, 'vec4', 'color', ColorValue()))
        self.addOutPlug(Plug('ScaleOutColor', self, 'vec4', 'color', ColorValue(), inParam=False))
        
    def customCode(self, name):
        return f'vec4 {self.outplugs["ScaleOutColor"].variable} = {self.inplugs["ScaleInColor"].variable} * {self.inplugs["ScaleFloat"].variable}'
        
class Vec4ToColorNode(Node):
    def __init__(self):
        super().__init__('Vec4 to Color')
        
        self.addInPlug(Plug('R', self, 'float', 'r', FloatValue()))
        self.addInPlug(Plug('G', self, 'float', 'g', FloatValue()))
        self.addInPlug(Plug('B', self, 'float', 'b', FloatValue()))
        self.addInPlug(Plug('A', self, 'float', 'a', FloatValue()))
        self.addOutPlug(Plug('Color', self, 'vec4', 'color', ColorValue()))
        
    def customCode(self, name):
        return f'vec4 {self.outplugs["Color"].variable} = vec4({self.inplugs["R"].variable}, {self.inplugs["G"].variable}, {self.inplugs["B"].variable}, {self.inplugs["A"].variable})'
        
class InvertColorNode(Node):
    def __init__(self):
        super().__init__('Invert Color')
        
        self.inplugs['inColor'] = Plug('inColor', self, 'vec4', 'color', ColorValue())
        self.outplugs['outColor'] = Plug('outColor', self, 'vec4', 'color', self.inplugs['inColor'], inParam=False)
        
    def customCode(self, name):
        return f'vec4 {self.outplugs["outColor"].variable} = vec4(1-{self.inplugs["inColor"].variable}.r, 1-{self.inplugs["inColor"].variable}.g, 1-{self.inplugs["inColor"].variable}.b, {self.inplugs["inColor"].variable}.a)'
        
class DivideNode(Node):
    def __init__(self):
        super().__init__('Divide')
        
        self.addInPlug(Plug('Divident', self, 'float', 'da', FloatValue()))
        self.addInPlug(Plug('Divisor', self, 'float', 'db', FloatValue()))
        self.addOutPlug( Plug('Result', self, 'float', 'r', FloatValue()) )
        
    def customCode(self, name):
        return f'float {self.outplugs["Result"].variable} = {self.inplugs["Divident"].variable} / {self.inplugs["Divisor"].variable}'
        
class OperatorNode(Node):
    def __init__(self):
        super().__init__('Operator (II)')
        
        self.addInPlug( Plug('Operator', self, 'float', 'o', StringValue('+'), declare_variable=False, internal = True) )
        self.addInPlug(Plug('From', self, 'float', 'sa', FloatValue()))
        self.addInPlug(Plug('What', self, 'float', 'sb', FloatValue()))
        self.addOutPlug( Plug('Result', self, 'float', 'r', FloatValue()) )
        
    def customCode(self, name):
        return f'float {self.outplugs["Result"].variable} = {self.inplugs["From"].variable} {self.inplugs["Operator"].value} {self.inplugs["What"].variable}'
        
class AddColorNode(Node):
    def __init__(self):
        super().__init__('Add Color')
        
        self.addInPlug(Plug('Color1', self, 'vec4', 'ca', ColorValue()))
        self.addInPlug(Plug('Color2', self, 'vec4', 'cb', ColorValue()))
        self.addOutPlug( Plug('Result', self, 'vec4', 'r', ColorValue()) )
        
    def customCode(self, name):
        return f'vec4 {self.outplugs["Result"].variable} = {self.inplugs["Color1"].variable} + {self.inplugs["Color2"].variable}'
        
class SmoothStepNode(Node):
    def __init__(self):
        super().__init__('Smooth Step')
        
        self.addInPlug( Plug('Edge1', self, 'float', 'ea', FloatValue()) )
        self.addInPlug( Plug('Edge2', self, 'float', 'eb', FloatValue()) )
        self.addInPlug( Plug('Interpolation', self, 'float', 'x', FloatValue()) )
        self.addOutPlug( Plug('Result', self, 'float', 'r', FloatValue()) )
        
    def customCode(self, name):
        return f'float {self.outplugs["Result"].variable} = smoothstep({self.inplugs["Edge1"].variable}, {self.inplugs["Edge2"].variable}, {self.inplugs["Interpolation"].variable})'
        
class PlotNode(Node):
    def __init__(self):
        super().__init__('Plot')
        
        self.addInPlug( Plug('Pct', self, 'float', 'p', FloatValue()) )
        self.addInPlug( Plug('Interp', self, 'float', 'i', FloatValue()) )
        self.addOutPlug( Plug('Result', self, 'float', 'r', FloatValue()) )
        
    def customCode(self, name):
        return f'float {self.outplugs["Result"].variable} = smoothstep({self.inplugs["Pct"].variable}-0.02,{self.inplugs["Pct"].variable},{self.inplugs["Interp"].variable}) - smoothstep({self.inplugs["Pct"].variable},{self.inplugs["Pct"].variable}+0.02,{self.inplugs["Interp"].variable})'
        
class FunctionINode(Node):
    def __init__(self):
        super().__init__('Function (I)')
        
        self.addInPlug( Plug('Function', self, 'float', 'f', StringValue('sin'), declare_variable=False, internal = True) )
        self.addInPlug( Plug('Type', self, 'float', 't', StringValue('float'), declare_variable=False, internal = True) )
        self.addInPlug( Plug('Param', self, 'float', 'p', FloatValue()) )
        self.addOutPlug( Plug('Result', self, 'float', 'r', FloatValue()) )
        
    def customCode(self, name):
        return f'{self.inplugs["Type"].value} {self.outplugs["Result"].variable} = {self.inplugs["Function"].value}({self.inplugs["Param"].variable})'

class FunctionIINode(Node):
    def __init__(self):
        super().__init__('Function (II)')
        
        self.addInPlug( Plug('Function', self, 'float', 'f', StringValue('step'), declare_variable=False, internal = True) )
        self.addInPlug( Plug('Type', self, 'float', 't', StringValue('float'), declare_variable=False, internal = True) )
        self.addInPlug( Plug('Param1', self, 'float', 'pa', FloatValue()) )
        self.addInPlug( Plug('Param2', self, 'float', 'pb', FloatValue()) )
        self.addOutPlug( Plug('Result', self, 'float', 'r', FloatValue()) )
        
    def customCode(self, name):
        return f'{self.inplugs["Type"].value} {self.outplugs["Result"].variable} = {self.inplugs["Function"].value}({self.inplugs["Param1"].variable}, {self.inplugs["Param2"].variable})'

class FunctionIIINode(Node):
    def __init__(self):
        super().__init__('Function (III)')
        
        self.addInPlug( Plug('Function', self, 'float', 'f', StringValue('vec3'), declare_variable=False, internal = True) )
        self.addInPlug( Plug('Type', self, 'float', 't', StringValue('vec3'), declare_variable=False, internal = True) )
        self.addInPlug( Plug('Param1', self, 'float', 'pa', FloatValue()) )
        self.addInPlug( Plug('Param2', self, 'float', 'pb', FloatValue()) )
        self.addInPlug( Plug('Param3', self, 'float', 'pc', FloatValue()) )
        self.addOutPlug( Plug('Result', self, 'float', 'r', FloatValue()) )
        
    def customCode(self, name):
        return f'{self.inplugs["Type"].value} {self.outplugs["Result"].variable} = {self.inplugs["Function"].value}({self.inplugs["Param1"].variable}, {self.inplugs["Param2"].variable}, {self.inplugs["Param3"].variable})'

class FunctionIVNode(Node):
    def __init__(self):
        super().__init__('Function (IV)')
        
        self.addInPlug( Plug('Function', self, 'float', 'f', StringValue('vec4'), declare_variable=False, internal = True) )
        self.addInPlug( Plug('Type', self, 'float', 't', StringValue('vec4'), declare_variable=False, internal = True) )
        self.addInPlug( Plug('Param1', self, 'float', 'pa', FloatValue()) )
        self.addInPlug( Plug('Param2', self, 'float', 'pb', FloatValue()) )
        self.addInPlug( Plug('Param3', self, 'float', 'pc', FloatValue()) )
        self.addInPlug( Plug('Param4', self, 'float', 'pc', FloatValue()) )
        self.addOutPlug( Plug('Result', self, 'float', 'r', FloatValue()) )
        
    def customCode(self, name):
        return f'{self.inplugs["Type"].value} {self.outplugs["Result"].variable} = {self.inplugs["Function"].value}({self.inplugs["Param1"].variable}, {self.inplugs["Param2"].variable}, {self.inplugs["Param3"].variable}, {self.inplugs["Param4"].variable})'

class FragCoordNode(Node):
    def __init__(self):
        super().__init__('Coordinates')
        
        self.addOutPlug(Plug('X', self, 'float', 'gl_FragCoord.x', FloatValue(), generate_variable=False, declare_variable=False))
        self.addOutPlug(Plug('Y', self, 'float', 'gl_FragCoord.y', FloatValue(), generate_variable=False, declare_variable=False))
        self.addOutPlug(Plug('Z', self, 'float', 'gl_FragCoord.z', FloatValue(), generate_variable=False, declare_variable=False))
        
class FragmentShaderNode(Node):
    def __init__(self):
        super().__init__('Fragment Shader')
        
        self.inplugs['Color'] = Plug('Color', self, 'vec4', 'color', ColorValue())
        self.outplugs['Pixel Color'] = Plug('Pixel Color', self, '', 'sg_FragColor', self.inplugs['Color'], False, False, inParam=False)
        
    def getGlobalCode(self):
        return 'out vec4 sg_FragColor;\n';
        
node_classes = {
            'Invert Color': InvertColorNode,
            'Scale Node': ScaleNode,
            'Random Color': UniformRandomColorNode,
            'Random Float': UniformRandomFloatNode,
            'Vec4 to Color': Vec4ToColorNode,
            'Frag Coords': FragCoordNode,
            'Divide': DivideNode,
            'Operator (II)': OperatorNode,
            'Smooth Step': SmoothStepNode,
            'Plot Line': PlotNode,
            'Add Color': AddColorNode,
            'Function (I)': FunctionINode,
            'Function (II)': FunctionIINode,
            'Function (III)': FunctionIIINode,
            'Function (IV)': FunctionIVNode,
        }
        
custom_nodes = {}

class NodeFactory:
    def getNodeNames():
        return list(node_classes.keys())+list(custom_nodes.keys())
        
    def getNewNode(name):
        if name in node_classes:
            return node_classes[name]()
        elif name in custom_nodes:
            _, outplugs = custom_nodes[name]
            node = Node(name)
            for plugname, rettype, variablename in outplugs:
                plug = Plug(plugname, node, rettype, variablename, FloatValue(), generate_variable=False, display=True, inParam=False, declare_variable=False)
                node.addOutPlug(plug)
                plug.editable = False
            return node
        else:
            return None

    def addCustomNode(name, outplugs):
        custom_nodes[name] = (name, outplugs)
    
class FragmentShaderGraph:
    def __init__(self):
        fsnode = FragmentShaderNode()
        fsnode.can_delete = False
        fsnode.location = [350, 20]
        self.nodes = [fsnode]
        self.requires_compilation = True
        self.uniforms = {}
        self.in_error = False
        
    def removeNode(self, rnode):
        self.nodes.remove(rnode)
        for node in self.nodes:
            for plug in node.inplugs.values():
                try:
                    if rnode==plug.value.parent:
                        plug.setDefaultValue()
                except:
                    pass
                    
    def prepare(self):
        self.uniforms.clear()
        for node in self.nodes:
            if isinstance(node, UniformNode):
                self.uniforms[node.name] = node.uniform
            for plug in node.inplugs.values():
                plug.declared = False
            for plug in node.outplugs.values():
                plug.declared = False
    
    def new( self ):
        self.uniforms.clear()
        self.nodes.clear()
        fsnode = FragmentShaderNode()
        fsnode.can_delete = False
        fsnode.location = [350, 20]
        self.nodes.append(fsnode)
        Plug.count = 1
        self.requires_compilation = True
        
    def updateVariableCount( self ):
        Plug.count = 1
        for node in self.nodes:
            for plug in node.inplugs.values():
                Plug.count += 1
            for plug in node.outplugs.values():
                Plug.count += 1
        
if __name__ == '__main__':
    g = FragmentShaderGraph()
    vtc = Vec4ToColorNode()
    fn = UniformRandomFloatNode()
    fc = FragCoordNode()
    dv = DivideNode()
    
    g.nodes.extend([vtc,fn,fc,dv])
    
    g.nodes[0].inplugs['Color'].setValue(vtc.outplugs['Color'])
    vtc.inplugs['R'].setValue(fn.outplugs['Uniform'])
    vtc.inplugs['G'].setValue(fc.outplugs['X'])
    vtc.inplugs['B'].setValue(dv.outplugs['Result'])
    vtc.inplugs['A'].setValue(dv.outplugs['Result'])
    
    code = ""
    globalcode = ""
    g.prepare()
    code, globalcode = g.nodes[0].generateCode('Pixel Color', code, globalcode)
    print('===============')
    print(globalcode)
    print('---------------')
    print(code)
    
    g.new()
    
    