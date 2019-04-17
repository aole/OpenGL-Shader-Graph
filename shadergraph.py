from OpenGL.GL import glUniform1f, glUniform2f, glUniform3f, glUniform4f
import random

uniforms = {}
UNIFORM_FUNCTION = [None, glUniform1f, glUniform2f, glUniform3f, glUniform4f]

class Plug:
    count = 1
    def __init__(self, name, parent, type, variable, value, generate_variable=True, display=True, inParam=True, declare_variable=True):
        self.name = name
        self.parent = parent
        self.type = type
        self.variable = variable
        self.value = value
        self.defaultValue = value
        self.inParam = inParam
        self.declared = False
        self.declare_variable = declare_variable
        
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
    def __init__(self):
        self.parent = None
        
    def __repr__(self):
        return self.__str__()
        
class ColorValue(Value):
    def __init__(self, color=(.9,.9,.9,1)):
        super().__init__()
        self.color = color
        
    def __str__(self):
        return f'vec4({self.color[0]}, {self.color[1]}, {self.color[2]}, {self.color[3]})'
    
    def GetColorInt(self):
        return (self.color[0]*255, self.color[1]*255, self.color[2]*255, self.color[3]*255)
    
    def SetColorInt(self, r, g, b):
        self.color = (r/255.0, g/255.0, b/255.0, 1.0)
        
class FloatValue(Value):
    def __init__(self, value=0.5):
        super().__init__()
        self.value = value
        
    def __str__(self):
        return f'{self.value}'
        
    def GetFloat(self):
        return str(round(self.value, 3))
        
    def SetFloat(self, value):
        try:
            self.value = float(value)
        except:
            pass
        
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
        for plugname, plug in self.inplugs.items():
            if isinstance(plug.value, Plug) and plug.value.parent!=self:
                if isinstance(plug.value.parent, UniformNode):
                    if not plug.value.declared:
                        globalcode += plug.value.value + ";\n"
                        plug.value.declared = True
                else:
                    if plug.value.declare_variable:
                        out, gc = plug.value.parent.generateCode(plug.value.name, code, globalcode)
                        code = out
                        globalcode = gc
            
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
        
        uniforms[name] = (UNIFORM_FUNCTION[count], function)
        
        self.plug = Plug('Uniform', self, type, name, "uniform "+type+" "+name, inParam=False, generate_variable=False)
        self.addOutPlug(self.plug)
        
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
        
class SolidColorNode(Node):
    def __init__(self):
        super().__init__('Solid Color')
        
        self.addOutPlug( Plug('Color', self, 'vec4', 'color', ColorValue((.1, .3, .7, 1))) )
        
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
        self.outplugs['gl_FragColor'] = Plug('gl_FragColor', self, '', 'gl_FragColor', self.inplugs['Color'], False, False, inParam=False)
        
node_classes = {
            'Solid Color': SolidColorNode,
            'Invert Color': InvertColorNode,
            'Scale Node': ScaleNode,
            'Random Color': UniformRandomColorNode,
            'Random Float': UniformRandomFloatNode,
            'Vec4 to Color': Vec4ToColorNode,
            'Frag Coords': FragCoordNode,
            'Divide': DivideNode
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
            print(outplugs)
            for plugname, rettype, variablename in outplugs:
                node.addOutPlug(Plug(plugname, node, rettype, variablename, FloatValue(), generate_variable=False, display=True, inParam=False, declare_variable=False))
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

    def removeNode(self, rnode):
        self.nodes.remove(rnode)
        for node in self.nodes:
            for plug in node.inplugs.values():
                try:
                    if rnode==plug.value.parent:
                        plug.setDefaultValue()
                        print('setDefaultValue')
                except:
                    pass
                    
    def prepare(self):
        for node in self.nodes:
            for plug in node.inplugs.values():
                plug.declared = False
            for plug in node.outplugs.values():
                plug.declared = False
                
if __name__ == '__main__':
    g = FragmentShaderGraph()
    vtc = Vec4ToColorNode()
    fn = UniformRandomFloatNode()
    fc = FragCoordNode()
    
    g.nodes[0].inplugs['Color'].setValue(vtc.outplugs['Color'])
    vtc.inplugs['R'].setValue(fn.outplugs['Uniform'])
    vtc.inplugs['G'].setValue(fn.outplugs['Uniform'])
    vtc.inplugs['B'].setValue(fc.outplugs['X'])
    
    code = ""
    globalcode = ""
    g.prepare()
    code, globalcode = g.nodes[0].generateCode('gl_FragColor', code, globalcode)
    print('===============')
    print(globalcode)
    print('---------------')
    print(code)
    