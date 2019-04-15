from OpenGL.GL import glUniform1f, glUniform2f, glUniform3f, glUniform4f
import random

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
        print(self,'->', value)
        
        
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
        fsnode.location = [200, 20]
        self.nodes = [fsnode]
        self.requires_compilation = True

        self.node_classes = (
            ('Solid Color', SolidColorNode),
            ('Invert Color', InvertColorNode),
            ('Scale Node', ScaleNode),
            ('Random Color', UniformRandomColorNode),
            ('Random Float', UniformRandomFloatNode)
        )
        
if __name__ == '__main__':
    g = FragmentShaderGraph()
    code = ""
    globalcode = ""
    code, globalcode = g.nodes[0].generateCode('gl_FragColor', code, globalcode)
    