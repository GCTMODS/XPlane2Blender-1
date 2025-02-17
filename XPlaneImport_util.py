#
# Copyright (c) 2004-2007 Jonathan Harris
#
# This code is licensed under version 2 of the GNU General Public License.
# http://www.gnu.org/licenses/gpl-2.0.html
#
# See ReadMe-XPlane2Blender.html for usage.
#

import sys
import Blender
from Blender import Armature, Object, Mesh, NMesh, Lamp, Image, Material, Texture, Draw, Window
from Blender.Mathutils import Matrix, RotationMatrix, TranslationMatrix, Vector
from XPlaneUtils import Vertex, UV, Face, PanelRegionHandler, getDatarefs, make_short_name

from math import radians
from os import listdir
from os.path import abspath, basename, curdir, dirname, join, normpath, sep, splitdrive, splitext
#import time

datarefs={}

class ParseError(Exception):
    def __init__(self, type, value=""):
        self.type = type
        self.value = value
    HEADER = 0
    TOKEN  = 1
    INTEGER= 2
    FLOAT  = 3
    NAME   = 4
    MISC   = 5
    PANEL  = 6
    TEXT   = ["Header", "Command", "Integer", "Number", "Name", "Misc", "Panel"]

class Mat:
    def __init__(self, d=[1,1,1], e=[0,0,0], s=0):
        self.d=d
        self.e=e
        self.s=s
        self.blenderMat=None

    def equals(self, other):
        return (self.d==other.d and self.e==other.e and self.s==other.s)

    def clone(self):
        return Mat(self.d, self.e, self.s)

    def getBlenderMat(self, force=False):
        if not self.blenderMat and (force or self.d!=[1,1,1] or self.e!=[0,0,0] or self.s):
            self.blenderMat=Material.New()
            self.blenderMat.rgbCol=self.d
            self.blenderMat.mirCol=self.e
            if self.e==[0,0,0]:
                self.blenderMat.emit=0
            else:
                self.blenderMat.emit=1
            self.blenderMat.spec=self.s
        return self.blenderMat

class MyMesh:
    # Flags
    LAYERMASK=7

    def __init__(self, faces=[], surface=None, deck=None, layers=1, anim=None, mat=None):
        self.faces=[]
        self.surface=surface	# Hard surface type or None
        self.deck=deck		# Hard surface deck type or None
        self.layers=layers	# LOD
        self.anim=anim		# (armob,offset,bonename)
        self.mat=mat
        self.addFaces(faces)

    def addFaces(self, faces):
        self.faces.extend(faces)

    #------------------------------------------------------------------------
    # are faces back-to-back duplicates?
    def isduplicate(self,faces):
        # print "isdupe", len(self.faces), len(faces)
        if len(faces[0].v)==3:	# assumes all new faces have same #vertices
            for face1 in faces:
                for face2 in self.faces:
                    if (len(face2.v)==3 and
                        face1.v[0].equals(face2.v[2]) and
                        face1.v[1].equals(face2.v[1]) and
                        face1.v[2].equals(face2.v[0])):
                        #print "dupe", face1, face2
                        return True
        elif len(faces[0].v)==4:
            for face1 in faces:
                for face2 in self.faces:
                    if (len(face2.v)==4 and
                        face1.v[0].equals(face2.v[3]) and
                        face1.v[1].equals(face2.v[2]) and
                        face1.v[2].equals(face2.v[1]) and
                        face1.v[3].equals(face2.v[0])):
                        #print "dupe", face1, face2
                        return True
        return False

    #------------------------------------------------------------------------
    def doimport(self,objimport,scene):

        mesh=Mesh.New(objimport.meshname)
        mesh.mode &= ~(Mesh.Modes.TWOSIDED|Mesh.Modes.AUTOSMOOTH)
        mesh.mode |= Mesh.Modes.NOVNORMALSFLIP

        mat=self.mat.getBlenderMat()
        if mat: mesh.materials+=[mat]

        centre=Vertex(0,0,0)
        if self.anim:
            #print self.anim[0], self.anim[1], self.anim[2]
            if self.anim[2]:
                boneloc=Vertex(self.anim[0].getData().bones[self.anim[2]].head['ARMATURESPACE'])
            else:	# Bone can be None if no_ref
                boneloc=Vertex(0,0,0)
            centre=boneloc-self.anim[1]
        #elif objimport.subroutine:
        #    n=0
        #    for f in self.faces:
        #        for vertex in f.v:
        #            n+=1
        #            centre.x+=vertex.x
        #            centre.y+=vertex.y
        #            centre.z+=vertex.z
        #    centre.x=round(centre.x/n,2)
        #    centre.y=round(centre.y/n,2)
        #    centre.z=round(centre.z/n,2)

        faces=[]
        verts=[]
        for f in self.faces:
            face=[]
            for v in f.v:
                face.append(len(verts))
                verts.append([v.x-centre.x, v.y-centre.y, v.z-centre.z])
            faces.append(face)
        mesh.verts.extend(verts)
        # ignoreDups because code below assumes face order matches up
        mesh.faces.extend(faces, ignoreDups=True)

        i=0
        for face in mesh.faces:
            f=self.faces[i]
            i+=1
            if not face: continue

            if f.flags&Face.PANEL:
                if f.region==None:
                    face.image = objimport.panelimage
                else:
                    face.image = objimport.regions[f.region]
            else:
                face.image = objimport.image

            face.uv=[Vector(uv.s, uv.t) for uv in f.uv]
            face.mat=0
            face.mode &= ~(Mesh.FaceModes.TWOSIDE|Mesh.FaceModes.TILES|
                           Mesh.FaceModes.DYNAMIC)
            if not f.flags&Face.HARD:
                face.mode |= Mesh.FaceModes.DYNAMIC
            if f.flags&Face.TWOSIDE:
                face.mode |= Mesh.FaceModes.TWOSIDE
            if not f.flags&Face.NPOLY:
                face.mode |= Mesh.FaceModes.TILES
            if f.flags&Face.FLAT:
                face.smooth=0
            else:
                face.smooth=1
            if f.flags&Face.ALPHA:
                face.transp=Mesh.FaceTranspModes.ALPHA
            else:
                face.transp=Mesh.FaceTranspModes.SOLID

            #assert len(face.v)==len(f.v) and len(face.uv)==len(f.uv)

        ob = Object.New('Mesh', objimport.meshname)
        ob.link(mesh)
        scene.objects.link(ob)
        if self.anim:
            #print "%s\t(%s) (%s) (%s)" % (self.anim[2], Vertex(self.anim[0].LocX, self.anim[0].LocY, self.anim[0].LocZ), Vertex(self.anim[0].getData().bones[self.anim[2]].head['ARMATURESPACE']), self.anim[1])
            ob.setLocation(self.anim[0].LocX+boneloc.x,
                           self.anim[0].LocY+boneloc.y,
                           self.anim[0].LocZ+boneloc.z)
            self.anim[0].makeParent([ob])
            if self.anim[2] and 'makeParentBone' in dir(self.anim[0]):	# new in 2.43
                #print self.anim[0], ob, self.anim[2]
                self.anim[0].makeParentBone([ob],self.anim[2])
        else:
            cur=objimport.globalmatrix.translationPart()
            ob.setLocation(centre.x+cur[0], centre.y+cur[1], centre.z+cur[2])
            r=objimport.globalmatrix.toEuler()
            ob.rot=((radians(r.x), radians(r.y), radians(r.z)))	# for 2.43

        if self.surface:
            ob.addProperty('surface', self.surface)
        if self.deck:
            ob.addProperty('deck', True, 'BOOL')
        if self.layers&MyMesh.LAYERMASK:
            ob.Layer=(self.layers&MyMesh.LAYERMASK)
        ob.getMatrix()		# force recalc in 2.43 - see Blender bug #5111

        # following must be after object linked to scene
        mesh.sel=True
        mesh.remDoubles(Vertex.LIMIT)
        mesh.sel=True
        mesh.calcNormals()	# calculate vertex normals
        mesh.sel=False

        if not objimport.subroutine: ob.select(1)
        return ob


#------------------------------------------------------------------------
#-- OBJimport --
#------------------------------------------------------------------------
class OBJimport:
    LAYER=[0,1,2,4]

    #------------------------------------------------------------------------
    def __init__(self, filename, subroutine=None):

        # Merging rules:
        # self.merge=1 - v7: merge if primitives have same flags
        #                v8: every TRIS statement is a new object
        # self.merge=2 - merge all triangles into one object

        # verbose - level of verbosity in console: 1-normal,2-chat,3-debug

        self.merge=1
        self.subroutine=subroutine	# object matrix
        if subroutine:	# Object is being merged into something else
            self.verbose=0
            (self.meshname,foo)=splitext(basename(filename))
            self.globalmatrix=subroutine
        else:
            self.verbose=1
            self.meshname='Mesh'
            self.globalmatrix=TranslationMatrix(Vector(Window.GetCursorPos())).resize4x4()

        if filename[0:2] in ['//', '\\\\']:
            # relative to .blend file
            self.filename=normpath(join(dirname(Blender.Get('filename')),
                                        filename[2:]))
        else:
            self.filename=abspath(filename)
        if sep=='\\':
            if self.filename[0] in ['/', '\\']:
                # Add Windows drive letter
                (drive,foo)=splitdrive(Blender.sys.progname)
                self.filename=drive.lower()+self.filename
            else:
                # Lowercase Windows drive lettter
                self.filename=filename[0].lower()+self.filename[1:]

        self.linesemi=0.025
        self.file=None		# file handle
        self.filelen=0		# for progress reports
        self.line=None		# current input line
        self.lineno=0		# for error reporting
        self.progress=-1
        self.fileformat=0	# 6, 7 or 8
        self.image=None		# texture image, iff scenery has texture
        self.panelimage=None
        self.regions=[]		# cockpit regions
        self.curmesh=[]		# unoutputted meshes
        self.nprim=0		# Number of X-Plane objects imported
        self.log=[]

        # flags controlling import
        self.layer=0
        self.lod=None		# list of lod limits
        self.fusecount=0

        # v8 structures
        self.vt=[]
        self.vline=[]
        self.vlight=[]
        self.idx=[]

        # attributes
        self.hard=False
        self.deck=None
        self.surface=None
        self.twoside=False
        self.flat=False		# >=7.30 defaults to smoothed
        self.alpha=False
        self.panel=False
        self.curregion=None
        self.poly=False
        self.drawgroup=None
        self.slung=0
        self.armob=None		# armature Object
        self.arm=None		# Armature
        self.action=None	# armature Action
        self.pendingbone=None	# current bone
        self.off=[]		# offset from current bone
        self.bones=[]		# Latest children
        self.currentrot=None	# current rotate_key axis, key number
        self.mat=Mat()
        self.mats=[self.mat]	# Cache of mats to prevent duplicates

    #------------------------------------------------------------------------
    def doimport(self):
        #clock=time.clock()	# Processor time
        if self.verbose:
            print "Starting OBJ import from " + self.filename
        Window.WaitCursor(1)

        self.file = open(self.filename, 'rU')
        self.file.seek(0,2)
        self.filelen=self.file.tell()
        self.file.seek(0)
        if not self.subroutine:
            Window.DrawProgressBar(0, "Opening ...")
        self.readHeader()
        scene=Blender.Scene.GetCurrent()
        layers=scene.layers
        scene.layers=[1,2,3]		# otherwise object centres not updated
        ob=self.readObjects(scene)
        scene.layers=layers
        scene.getRenderingContext().currentFrame(1)
        scene.makeCurrent()		# for pose in 2.42 - Blender bug #4696
        scene.update(1)
        if not self.subroutine:
            Window.DrawProgressBar(1, "Finished")
            Window.WaitCursor(0)
        #print "%s CPU time\n" % (time.clock()-clock)
        if self.verbose:
            Window.RedrawAll()
            print "Finished - imported %s primitives\n" % self.nprim
            if not self.log: self.log=['OK']
            Draw.PupMenu(("Imported %s primitives%%t|" % self.nprim)+'|'.join(self.log))
        return ob

    #------------------------------------------------------------------------
    def getInput(self, optional=False):
        try:
            return self.line.pop(0)
        except IndexError:
            if optional:
                return None
            else:
                raise ParseError(ParseError.MISC)

    #------------------------------------------------------------------------
    def getInt(self):
        try:
            return int(self.line.pop(0))
        except IndexError:
            raise ParseError(ParseError.INTEGER)
        except ValueError:
            raise ParseError(ParseError.INTEGER, c)

    #------------------------------------------------------------------------
    def getFloat(self):
        try:
            return float(self.line.pop(0))
        except IndexError:
            raise ParseError(ParseError.FLOAT)
        except ValueError:
            raise ParseError(ParseError.FLOAT, c)

    #------------------------------------------------------------------------
    def getCol(self):
        if self.fileformat<8:
            return [self.getFloat()/10.0 for i in range(3)]
        else:
            return [self.getFloat() for i in range(3)]

    #------------------------------------------------------------------------
    def getAttr(self):
        return [self.getFloat() for i in range(3)]

    #------------------------------------------------------------------------
    def getVertex(self):
        v=[self.getFloat() for i in range(3)]
        # Rotate to Blender format
        return Vertex(round( v[0],Vertex.ROUND),
                      round(-v[2],Vertex.ROUND),
                      round( v[1],Vertex.ROUND))

    #------------------------------------------------------------------------
    def getUV(self):
        u=self.getFloat()
        v=self.getFloat()
        return UV(u,v)

    #------------------------------------------------------------------------
    def getCR(self, optional=False):
        while True:
            line=self.file.readline()
            self.lineno+=1
            if not line:
                if optional:
                    return False
                else:
                    raise ParseError(ParseError.MISC, 'Unexpected <EOF>')
            self.line=line.split('#')[0].split('//')[0].split()
            if self.line:
                if self.verbose>2: print 'Input:\t%s' % self.line
                return True
            elif line.startswith('####_'):
                # check for special comments
                self.line=[line.strip()]
                if self.verbose>2: print 'Input:\t%s' % self.line
                return True
            elif not optional:
                raise ParseError(ParseError.MISC, 'Unexpected <EOL>')

    #------------------------------------------------------------------------
    def readHeader(self):
        c=self.file.readline().strip()
        if c.startswith("\xef\xbb\xbf"): c=c[3:]	# skip UTF-8 BOM
        if self.verbose>2: print 'Input:\t"%s"' % c
        if not c in ['A', 'I']:
            raise ParseError(ParseError.HEADER)

        c = self.file.readline().split()
        self.lineno=2
        if not c: raise ParseError(ParseError.HEADER)
        if self.verbose>2: print 'Input:\t"%s"' % c[0]
        if c[0]=="2":
            self.fileformat=6
            if self.verbose>1: print "Info:\tThis is an X-Plane v6 format file"
        elif c[0]=="700":
            if self.file.readline().split('#')[0].split('//')[0].split()[0]!="OBJ":
                raise ParseError(ParseError.HEADER)
            self.fileformat=7
            self.lineno=3
            if self.verbose>1: print "Info:\tThis is an X-Plane v7 format file"
        elif c[0]=="800":
            if self.file.readline().split('#')[0].split('//')[0].split()[0]!="OBJ":
                raise ParseError(ParseError.HEADER)
            self.fileformat=8
            self.lineno=3
            if self.verbose>1: print "Info:\tThis is an X-Plane v8 format file"
        else:
            raise ParseError(ParseError.HEADER)

        while True:
            line=self.file.readline()
            self.lineno+=1
            if not line: raise ParseError(ParseError.MISC, 'Unexpected <EOF>')
            tex = line.split('#')[0].split('//')[0].strip()
            if tex[:7] == 'GLOBAL_': continue
            if tex == 'TILTED': continue
            if tex: break

        # read texture
        if self.fileformat>=8:
            if not tex.startswith("TEXTURE"):
                raise ParseError(ParseError.HEADER)
            tex=tex[7:].strip()

        if tex.lower() in ['', 'none']:
            self.image=Image.New('none',1024,1024,24)
            if self.verbose>1:
                print "Info:\tNo texture"
            return

        base=tex.replace(':',sep)
        base='.'.join(base.split('.')[0:-1])
        # Look for texture in . and "../custom object textures"
        dirs=[dirname(self.filename)]
        l=self.filename.rfind('custom objects')
        if l!=-1:
            dirs.append(self.filename[:l]+'custom object textures')
        for subdir in dirs:
            for extension in ['.dds', '.DDS', '.png', '.PNG', '.bmp', '.BMP']:
                texname=normpath(subdir+sep+base+extension)
                #print "Trying texture %s as %s." % (tex, texname)
                try:
                    file = open(texname, "rb")
                except IOError:
                    pass
                else:
                    # Detect and fix up spaces in texture file name
                    if ' ' in base:
                        newname=normpath(subdir+sep+base.replace(' ','_')+
                                         extension)
                        newfile=open(newname, "wb")
                        newfile.write(file.read())
                        newfile.close()
                        texname=newname
                        print 'Info:\tCreated new texture file "%s"' % texname
                        self.log.append('Created new texture file "%s"' % texname)
                    elif self.verbose>1:
                        print 'Info:\tUsing texture file "%s"' % texname
                    file.close()
                    try:
                        self.image = Image.Load(texname)
                        self.image.getSize()	# force load
                    except:
                        print 'Warn:\tCannot read texture file "%s"' % texname
                        self.log.append('Cannot read texture file "%s"' % texname)
                        self.image=Image.New(basename(texname),1024,1024,24)
                    return

        self.image=Image.New(basename(base),1024,1024,24)
        print 'Warn:\tTexture file "%s" not found' % base
        self.log.append('Texture file "%s" not found' % base)

    #------------------------------------------------------------------------
    def readObjects (self, scene):

        while True:
            if not self.subroutine:
                pos=self.file.tell()
                progress=pos*50/self.filelen
                # only update progress bar if need to
                if self.progress!=progress:
                    Window.DrawProgressBar(float(pos)*0.5/self.filelen,
                                           "Importing %s%% ..." % progress)
                    self.progress=progress

            if not self.getCR(True): break

            t=self.line.pop(0)
            if self.fileformat==6:
                try:
                    t=int(t)
                    if self.verbose>2: print 'Token:\t%d' % t
                except:
                    raise ParseError(ParseError.TOKEN, t)

            if t in ['end', 99]:
                break

            # v8

            elif t=='COCKPIT_REGION':
                if not self.panelimage:
                    # first region
                    self.getpanel()
                    h=PanelRegionHandler().New(self.panelimage)
                else:
                    h=PanelRegionHandler()
                xoff=self.getInt()
                yoff=self.getInt()
                width=self.getInt()-xoff
                height=self.getInt()-xoff
                self.regions.append(h.addRegion(xoff, yoff, width, height))

            elif t=='VT':
                v=self.getVertex()
                n=self.getVertex()	# normal
                uv=self.getUV()
                self.vt.append((v,uv,n))

            elif t=='VLINE':
                v=self.getVertex()
                c=self.getCol()
                self.vline.append((v,c))

            elif t=='VLIGHT':
                v=self.getVertex()
                c=self.getCol()
                self.vlight.append((v,c))

            elif t=='IDX10':
                self.idx.extend([self.getInt() for i in range(10)])

            elif t=='IDX':
                self.idx.append(self.getInt())

            elif t=='LIGHTS':
                self.addpendingbone()
                a=self.getInt()
                b=self.getInt()
                for i in range(a,a+b):
                    (v,c)=self.vlight[i]
                    self.addLamp(scene,v,c)

            elif t=='LIGHT_NAMED':
                self.addpendingbone()
                name=self.getInput()
                v=self.getVertex()
                self.addLamp(scene,v,None,name)

            elif t=='LIGHT_CUSTOM':
                self.addpendingbone()
                v=self.getVertex()
                rgba=[self.getFloat() for i in range(4)]
                s=self.getFloat()
                uv=[self.getFloat() for i in range(4)]
                name=self.getInput()
                self.addCustomLight(scene,v,rgba,s,uv,name)

            elif t=='LINES':
                self.addpendingbone()
                a=self.getInt()
                b=self.getInt()
                for i in range(a,a+b,2):
                    v=[]
                    for j in range(i,i+2):
                        (vj,cj)=self.vline[self.idx[j]]
                        v.append(vj)
                        c=cj	# use second colour value
                    self.addLine(scene,v,c)

            elif t=='TRIS':
                self.addpendingbone()
                a=self.getInt()
                b=self.getInt()
                self.addTris(scene,t,a,b)

            elif t=='ANIM_begin':
                if not self.arm:
                    self.off=[Vertex(0,0,0)]
                    self.bones=[None]
                    self.armob = Object.New("Armature")
                    self.arm=Armature.Armature("Armature")
                    self.arm.drawNames=True
                    self.arm.drawType=Armature.STICK
                    self.arm.restPosition=True	# for easier parenting
                    self.armob.link(self.arm)
                    cur=self.globalmatrix.translationPart()
                    self.armob.setLocation(cur[0], cur[1], cur[2])
                    v=self.globalmatrix.toEuler()
                    self.armob.rot=((radians(v.x), radians(v.y), radians(v.z)))	# for 2.43
                    self.armob.getMatrix()		# force recalc in 2.43 - see Blender bug #5111
                    self.action = Armature.NLA.NewAction()
                    self.action.setActive(self.armob)
                    self.arm.makeEditable()
                else:
                    self.addpendingbone()
                    self.off.append(self.off[-1])
                    self.bones.append(None)

            elif t=='ANIM_end':
                if not len(self.off):
                    raise ParseError(ParseError.MISC,
                                     'ANIM_END with no matching ANIM_BEGIN')
                self.addpendingbone()
                self.off.pop()
                self.bones.pop()
                if not self.off:
                    # Back at top level
                    #print self.off, self.bones
                    self.arm.restPosition=False
                    self.arm.update()
                    scene.objects.link(self.armob)
                    if self.layer:
                        self.armob.Layer=OBJimport.LAYER[self.layer]
                    self.arm=None
                    self.armob=None
                    self.action=None

            elif t=='ANIM_trans':
                p1=self.getVertex()
                p2=self.getVertex()
                v1=self.getFloat()
                v2=self.getFloat()
                dataref=self.getInput(True)
                dataref=dataref and dataref.split('/') or 'none'	# can be omitted if just a shift
                name=dataref[-1]
                self.off[-1]=self.off[-1]+p1
                if not self.pendingbone:
                    # skip translate back added by AC3D plugin
                    if len(self.bones)==1:
                        # first bone in Armature - move armature location
                        self.armob.setLocation(self.off[-1].x+self.armob.LocX, self.off[-1].y+self.armob.LocY, self.off[-1].z+self.armob.LocZ)
                        self.armob.getMatrix()		# force recalc in 2.43 - see Blender bug #5111
                        self.off[-1]=Vertex(0,0,0)
                    else:
                        # first bone at this level - adjust previous tail
                        #self.arm.bones[self.bones[-2]].tail=self.off[-1].toVector(3)
                        pass
                    if not p1.equals(p2):
                        # not just a shift
                        if '[' in name: name=name[:name.index('[')]
                        if len(dataref)>1 and (not name in datarefs or not datarefs[name]):
                            # custom or ambiguous dataref
                            self.addArmProperty(name, '/'.join(dataref[:-1]))
                        if v1!=0: self.addArmProperty(dataref[-1]+'_v1', v1)
                        if v2!=1: self.addArmProperty(dataref[-1]+'_v2', v2)
                        head=self.off[-1]
                        #tail=self.off[-1]+(p2-p1).normalize()*0.1
                        tail=self.off[-1]+Vertex(0,0.1,0)
                        m1=Matrix().identity().resize4x4()
                        m2=TranslationMatrix((p2-p1).toVector(4))
                        self.pendingbone=(dataref[-1], head, tail, [m1,m2])

            elif t=='ANIM_trans_begin':
                dataref=self.getInput().split('/')
                name=dataref[-1]
                self.pendingbone=(dataref[-1], None, None, [])
                if '[' in name: name=name[:name.index('[')]
                if len(dataref)>1 and (not name in datarefs or not datarefs[name]):
                    # custom or ambiguous dataref
                    self.addArmProperty(name, '/'.join(dataref[:-1]))

            elif t=='ANIM_trans_key':
                v=self.getFloat()
                p=self.getVertex()
                (dataref, head, tail, m)=self.pendingbone
                if m:
                    m.append(TranslationMatrix(p.toVector(3)-m[0].translationPart()))
                    self.addArmProperty('%s_v%s' % (dataref, len(m)), v)
                else:	# first
                    self.off[-1]=self.off[-1]+p
                    m.append(Matrix().identity().resize4x4())
                    if v: self.addArmProperty('%s_v1' % dataref, v)

            elif t=='ANIM_trans_end':
                if len(self.bones)==1:
                    # first bone in Armature - move armature location
                    self.armob.setLocation(self.off[-1].x+self.armob.LocX, self.off[-1].y+self.armob.LocY, self.off[-1].z+self.armob.LocZ)
                    self.armob.getMatrix()		# force recalc in 2.43 - see Blender bug #5111
                    self.off[-1]=Vertex(0,0,0)
                else:
                    # first bone at this level - adjust previous tail
                    #self.arm.bones[self.bones[-2]].tail=self.off[-1].toVector(3)
                    pass
                (dataref, head, tail, m)=self.pendingbone
                head=self.off[-1]
                tail=self.off[-1]+Vertex(0,0.1,0)
                self.pendingbone=(dataref[-1], head, tail, m)

            elif t=='ANIM_rotate':
                p=self.getVertex()
                r1=self.getFloat()
                r2=self.getFloat()
                v1=self.getFloat()
                v2=self.getFloat()
                dataref=self.getInput(True)
                dataref=dataref and dataref.split('/') or 'none'	# 3DSMax exporter sometimes emits a static rotation with no DataRef!
                while r2>=360 or r2<=-360:
                    # hack!
                    r2/=2
                    v2/=2
                name=dataref[-1]
                if '[' in name: name=name[:name.index('[')]
                if len(dataref)>1 and (not name in datarefs or not datarefs[name]):
                    # custom or ambiguous dataref
                    self.addArmProperty(name, '/'.join(dataref[:-1]))
                if v1!=0: self.addArmProperty(dataref[-1]+'_v1', v1)
                if v2!=1: self.addArmProperty(dataref[-1]+'_v2', v2)
                m1=RotationMatrix(r1,4,'r',p.toVector(3))
                m2=RotationMatrix(r2,4,'r',p.toVector(3))
                m=[m1,m2]
                if self.pendingbone:
                    (name, head, tail, o)=self.pendingbone
                    if name!=dataref[-1]: #or m2[3]==Vector(0,0,0,1):
                        # Different dataref - new bone!
                        self.addpendingbone()
                    else:
                        m=[m1*o[0],m2*o[1]]+o[2:]
                else:
                    head=self.off[-1]
                    tail=self.off[-1]+Vertex(0,0.1,0)
                self.pendingbone=(dataref[-1], head, tail, m)

            elif t=='ANIM_rotate_begin':
                self.currentrot=(self.getVertex().toVector(3), 0)
                dataref=self.getInput().split('/')
                name=dataref[-1]
                if '[' in name: name=name[:name.index('[')]
                if len(dataref)>1 and (not name in datarefs or not datarefs[name]):
                    # custom or ambiguous dataref
                    self.addArmProperty(name, '/'.join(dataref[:-1]))
                m=[]
                if self.pendingbone:
                    (name, head, tail, m)=self.pendingbone
                    if name!=dataref[-1]: #or m2[3]==Vector(0,0,0,1):
                        # Different dataref - new bone!
                        self.addpendingbone()
                else:
                    head=self.off[-1]
                    tail=self.off[-1]+Vertex(0,0.1,0)
                self.pendingbone=(dataref[-1], head, tail, m)

            elif t=='ANIM_rotate_key':
                v=self.getFloat()
                r=self.getFloat()
                (p,idx)=self.currentrot
                (dataref, head, tail, m)=self.pendingbone
                if idx or v: self.addArmProperty('%s_v%s' % (dataref,idx+1), v)
                n=RotationMatrix(r,4,'r',p)
                if idx<len(m):
                    m[idx]=n*m[idx]
                else:
                    m.append(n)
                self.currentrot=(p,idx+1)

            elif t=='ANIM_rotate_end':
                self.currentrot=None

            elif t=='ANIM_keyframe_loop':
                n=self.getFloat()
                (dataref, head, tail, m)=self.pendingbone
                self.addArmProperty(dataref+'_loop', n)

            elif t in ['ANIM_show', 'ANIM_hide']:
                v1=self.getFloat()
                v2=self.getFloat()
                dataref=self.getInput().split('/')
                name=dataref[-1]
                if '[' in name: name=name[:name.index('[')]
                if len(dataref)>1 and not name in datarefs:
                    self.armob.addProperty(name,'/'.join(dataref[:-1])+'/')
                if t=='ANIM_show':
                    self.armob.addProperty(dataref[-1]+'_show_v1', v1)
                    self.armob.addProperty(dataref[-1]+'_show_v2', v2)
                else:
                    self.armob.addProperty(dataref[-1]+'_hide_v1', v1)
                    self.armob.addProperty(dataref[-1]+'_hide_v2', v2)

            elif t=='ATTR_hard':
                self.hard = True
                self.deck = False
                self.surface = self.getInput(True)
                if self.surface=='object': self.surface=None
            elif t=='ATTR_hard_deck':
                self.hard = True
                self.deck = True
                self.surface = self.getInput(True)
                if self.surface=='object': self.surface=None
            elif t=='ATTR_no_hard':
                self.hard = False
                self.deck = None
                self.surface = None

            elif t =='ATTR_cockpit':
                if not self.panelimage:
                    # first region
                    self.getpanel()
                    h=PanelRegionHandler()
                    if h: h.New(self.panelimage)	# zap exisiting regions
                self.panel = True
                self.getpanel()
                self.curregion=None
            elif t =='ATTR_cockpit_region':
                self.panel = True
                self.getpanel()
                self.curregion=int(self.getFloat())
            elif t=='ATTR_no_cockpit':
                self.panel = False
                self.curregion=None

            elif t in ['smoke_black', 'smoke_white']:
                self.addpendingbone()
                v=self.getVertex()
                c=self.getFloat()
                self.addLamp(scene,v,c,t)

            elif t in ['EXPORT', 'POINT_COUNTS', 'TEXTURE_LIT', 'TEXTURE_NORMAL']:
                pass	# Silently ignore

            # v7

            elif t=='light':
                self.getCR()
                v=self.getVertex()
                c=self.getCol()
                self.addLamp(scene,v,c)

            elif t=='line':
                v = []
                for i in range(2):
                    self.getCR()
                    v.append(self.getVertex())
                    c=self.getCol()	# use second colour value
                self.addLine(scene,v,c)

            elif t=='tri':
                v = []
                uv = []
                for i in range(3):
                    self.getCR()
                    v.append(self.getVertex())
                    uv.append(self.getUV())
                self.addFan(scene,t,v,uv)

            elif t in ['quad', 'quad_hard', 'quad_movie', 'quad_cockpit']:
                if t=='quad_hard':
                    self.hard=True
                elif t=='quad_cockpit':
                    self.panel=True
                v = []
                uv = []
                for i in range(4):
                    self.getCR()
                    v.append(self.getVertex())
                    uv.append(self.getUV())
                self.addStrip(scene,t,v,uv,[3,2,1,0])
                self.hard=False
                self.panel=False

            elif t=='polygon':
                # add centre point, duplicate first point, use Tri_Fan
                v = []
                uv = []
                cv = [0,0,0]
                cuv = [0,0]
                n = self.getInt()
                for i in range(n):
                    self.getCR()
                    v.append(self.getVertex())
                    cv[0]+=v[i].x
                    cv[1]+=v[i].y
                    cv[2]+=v[i].z
                    uv.append(self.getUV())
                    cuv[0]+=uv[i].s
                    cuv[1]+=uv[i].t
                cv[0]/=n
                cv[1]/=n
                cv[2]/=n
                cuv[0]/=n
                cuv[1]/=n
                v.append(v[0])
                uv.append(uv[0])
                v.insert(0,Vertex(cv[0],cv[1],cv[2]))
                uv.insert(0,UV(cuv[0],cuv[1]))
                self.addFan(scene,t,v,uv)

            elif t=='quad_strip':
                n = self.getInt()
                v = []
                uv = []
                while n:
                    self.getCR()
                    v.append(self.getVertex())
                    uv.append(self.getUV())
                    if self.line:
                        # second pair on same line
                        v.append(self.getVertex())
                        uv.append(self.getUV())
                        n-=2
                    else:
                        n-=1
                self.addStrip(scene,t,v,uv,[1,0,2,3])

            elif t=='tri_strip':
                v = []
                uv = []
                n = self.getInt()
                for i in range(n):
                    self.getCR()
                    v.append(self.getVertex())
                    uv.append(self.getUV())
                self.addStrip(scene,t,v,uv,[0,1,2])

            elif t=='tri_fan':
                v = []
                uv = []
                n = self.getInt()
                for i in range(n):
                    self.getCR()
                    v.append(self.getVertex())
                    uv.append(self.getUV())
                self.addFan(scene,t,v,uv)

            # v6

            elif t==1:	# light
                c=self.getCol()
                self.getCR()
                v=self.getVertex()
                self.addLamp(scene,v,c)

            elif t==2:	# line
                v = []
                c=self.getCol()
                for i in range(2):
                    self.getCR()
                    v.append(self.getVertex())
                self.addLine(scene,v,c)

            elif t==3:	# tri
                v = []
                uv = []
                for i in range(4):
                    uv.append(self.getFloat())	# s s t t
                for i in range(3):
                    self.getCR()
                    v.append(self.getVertex())
                # UV order appears to be arbitrary
                self.addFan(scene,t,v,[UV(uv[1],uv[3]),
                                        UV(uv[1],uv[2]),
                                        UV(uv[0],uv[2])])
            elif t in [4,5,8]:	# quad, quad_hard, quad_movie
                if t==5:
                    self.hard=True
                v = []
                uv = []
                for i in range(4):
                    uv.append(self.getFloat())
                for i in range(4):
                    self.getCR()
                    v.append(self.getVertex())
                self.addStrip(scene,t,v,[UV(uv[1],uv[3]),
                                         UV(uv[1],uv[2]),
                                         UV(uv[0],uv[2]),
                                         UV(uv[0],uv[3])],
                              [3,2,1,0])
                self.hard=False

            elif isinstance(t,int) and t<0:	# Quad strip
                n = -t	# number of pairs
                v = []
                uv = []
                for i in range(n):
                    self.getCR()
                    v.append(self.getVertex())
                    v.append(self.getVertex())
                    s=self.getUV()		# s s t t
                    t=self.getUV()
                    uv.append(UV(s.s,t.s))
                    uv.append(UV(s.t,t.t))
                self.addStrip(scene,'quad_strip',v,uv,[1,0,2,3])

            # generic state

            elif t=='slung_load_weight':
                self.slung=self.getFloat()

            elif t=='ATTR_shade_flat':
                self.flat = True
            elif t=='ATTR_shade_smooth':
                self.flat = False

            elif t=='ATTR_poly_os':
                n = self.getFloat()
                self.poly = (n!=0)

            elif t=='ATTR_depth':
                self.poly=False
            elif t=='ATTR_no_depth':
                self.poly=True

            elif t=='ATTR_cull':
                self.twoside = False
            elif t in ['ATTR_no_cull', 'ATTR_nocull']:
                self.twoside = True

            elif t=='####_alpha':
                self.alpha = True
            elif t=='####_no_alpha':
                self.alpha = False

            elif t.startswith('####_'):	# eg ####_group
                pass

            elif t=='ATTR_layer_group':
                self.drawgroup=(self.getInput(), self.getInt())

            elif t=='ATTR_LOD':
                x=int(self.getFloat())
                y=int(self.getFloat())
                if not self.layer:
                    print "Info:\tMultiple Levels Of Detail found"
                    self.log.append("Multiple Levels Of Detail found")
                if self.layer==0 and x!=0:
                    self.lod=[x,1000,4000,10000]
                if self.layer<3:
                    self.layer+=1
                if y!=[0,1000,4000,10000][self.layer]:
                    if not self.lod: self.lod=[0,1000,4000,10000]
                    self.lod[self.layer]=y
                # Reset attributes
                self.hard=False
                self.twoside=False
                self.flat=False
                self.alpha=False
                self.panel=False
                self.curregion=None
                self.poly=False
                self.mat=self.mats[0]

            elif t=='ATTR_reset':
                self.hard=False
                self.twoside=False
                self.flat=False
                self.alpha=False
                self.panel=False
                self.curregion=None
                self.poly=False
                self.mat=self.mats[0]

            elif t in ['ATTR_diffuse_rgb', 'ATTR_difuse_rgb']:
                self.mat=self.mat.clone()
                self.mat.d=self.getAttr()
                for m in self.mats:
                    if self.mat.equals(m):
                        self.mat=m
                else:
                    self.mats.append(self.mat)

            elif t=='ATTR_emission_rgb':
                self.mat=self.mat.clone()
                self.mat.e=self.getAttr()
                for m in self.mats:
                    if self.mat.equals(m):
                        self.mat=m
                else:
                    self.mats.append(self.mat)

            elif t=='ATTR_shiny_rat':
                self.mat=self.mat.clone()
                self.mat.s=self.getFloat()
                for m in self.mats:
                    if self.mat.equals(m):
                        self.mat=m
                else:
                    self.mats.append(self.mat)

            elif self.fileformat>6 and (t.startswith('ATTR_') or t.startswith('GLOBAL_')):
                print 'Warn:\tIgnoring unsupported "%s"' % t
                self.log.append('Ignoring unsupported "%s"' % t)

            else:
                pass
                #raise ParseError(ParseError.MISC,'Unrecognised Command "%s"' % t)


        # global attributes
        if (self.drawgroup or self.lod or self.slung) and not self.subroutine:
            ob = Object.New("Empty", "Attributes")
            ob.drawSize=0.1
            #ob.drawMode=2	# 2=OB_PLAINAXES
            if self.drawgroup:
                ob.addProperty("group_%s" % self.drawgroup[0],
                               self.drawgroup[1])
            if self.slung:
                ob.addProperty("slung_load_weight", self.slung)
            if self.lod:
                for i in range(4):
                    if self.lod[i]!=[0,1000,4000,10000][i]:
                        ob.addProperty("LOD_%d" % i, self.lod[i])
            scene.objects.link(ob)
            cur=Window.GetCursorPos()
            ob.setLocation(cur[0], cur[1], cur[2])

        # write meshes
        obs=[]
        for i in range(len(self.curmesh)):
            if not self.subroutine:
                Window.DrawProgressBar(0.9+(i/10.0)/len(self.curmesh),
                                       "Adding %d%% ..." % (
                    90+(i*10.0)/len(self.curmesh)))
            obs.append(self.curmesh[i].doimport(self,scene))
        return obs

    #------------------------------------------------------------------------
    def addLamp(self, scene, v, c, name=None):
        propname=None
        e=1.0
        if name:	# named light
            # try to be helpful - some names that we know about
            if name=='smoke_black':
                e=c
                c=[0,0,0]
            elif name=='smoke_white':
                e=c
                c=[0.5,0.5,0.5]
            elif name in ['airplane_nav_left', 'airplane_beacon'] or name.endswith('_red'):
                c=[1,0,0]
            elif name in ['airplane_nav_right', 'taxi_center_light', 'taxi_g'] or name.endswith('_green'):
                c=[0,1,0]
            elif name in ['taxi_edge_blue', 'taxi_b'] or name.endswith('_blue'):
                c=[0,0,1]
            elif name in ['airplane_strobe', 'airplane_landing', 'airplane_taxi'] or name.endswith('_white'):
                c=[1,1,1]
            else:	# dunno
                c=[0.75,0.75,0.75]
            if len(name)>17 or 'lamp' in name.lower().split():
                # Blender name limit is 17
                propname=name
                name='Named light'
        elif c[0]==1.1 and c[1]==1.1 and c[2]==1.1:
            name="airplane_nav_left"
            c=[1,0,0]
        elif c[0]==2.2 and c[1]==2.2 and c[2]==2.2:
            name="airplane_nav_right"
            c=[0,1,0]
        elif ((c[0]==9.9 and c[1]==9.9 and c[2]==9.9) or
            (c[0]==3.3 and c[1]==3.3 and c[2]==3.3)):
            name="airplane_beacon"
            c=[1,0,0]
        elif ((c[0]==9.8 and c[1]==9.8 and c[2]==9.8) or
              (c[0]==4.4 and c[1]==4.4 and c[2]==4.4)):
            name="airplane_strobe"
            c=[1,1,1]
        elif c[0]==5.5 and c[1]==5.5 and c[2]==5.5:
            name="airplane_landing"
            c=[1,1,1]
        elif c[0]==9.7 and c[1]==9.7 and c[2]==9.7:
            name="Traffic"
            c=[1,1,0]
        elif c[0]<0 or c[1]<0 or c[2]<0:
            name="Flash"
            c=[abs(c[0]),abs(c[1]),abs(c[2])]
        else:
            name="Lamp"

        if self.verbose>1:
            print 'Info:\tImporting Lamp at line %s "%s"' % (self.lineno, name)
        lamp=Lamp.New("Lamp", name)
        lamp.col=c
        lamp.energy=e
        lamp.dist=4.0	# arbitrary - stop lamp colouring whole object
        #amp.mode |= Lamp.Modes.Sphere
        ob = Object.New("Lamp", name)
        if propname: ob.addProperty('name', propname)
        ob.link(lamp)
        scene.objects.link(ob)
        if self.layer:
            ob.Layer=OBJimport.LAYER[self.layer]
        if self.armob:
            if self.bones:
                boneloc=Vertex(self.arm.bones[self.bones[-1]].head)
            else:	# Bone can be None if no_ref
                boneloc=Vertex(0,0,0)
            centre=v+boneloc-self.off[-1]
            ob.setLocation(self.armob.LocX+centre.x,
                           self.armob.LocY+centre.y,
                           self.armob.LocZ+centre.z)
            self.armob.makeParent([ob])
            if 'makeParentBone' in dir(self.armob):	# new in 2.43
                self.armob.makeParentBone([ob],self.bones[-1])
        else:
            cur=self.globalmatrix.translationPart()
            ob.setLocation(v.x+cur[0], v.y+cur[1], v.z+cur[2])
            r=self.globalmatrix.toEuler()
            ob.rot=((radians(r.x), radians(r.y), radians(r.z)))	# for 2.43
        ob.getMatrix()		# force recalc in 2.43 - see Blender bug #5111
        self.nprim+=1

    #------------------------------------------------------------------------
    def addCustomLight(self,scene,v,rgba,size,uv,dataref):
        if dataref in ['none', 'NULL']:
            name='Custom light'
            dataref=None
        else:
            dataref=dataref.split('/')
            name=dataref[-1]
        if self.verbose>1:
            print 'Info:\tImporting Custom Light at line %s "%s"' % (self.lineno, name)

        # Custom lights shouldn't be merged, so add immediately
        clampedrgba=[]
        for i in range(4):
            if 0<=rgba[i]<=1:
                clampedrgba.append(round(rgba[i],3))
            else:
                clampedrgba.append(1.0)
        uv=tuple([round(uv[i],3) for i in range(4)])

        for mat in Material.Get():
            if (mat.mode&(Material.Modes.HALO|Material.Modes.HALOTEX)==(Material.Modes.HALO|Material.Modes.HALOTEX) and
                round(mat.R,3)==clampedrgba[0] and
                round(mat.G,3)==clampedrgba[1] and
                round(mat.B,3)==clampedrgba[2] and
                round(mat.alpha,3)==clampedrgba[3] and
                mat.haloSize==size):
                mtex=mat.getTextures()[0]
                if mtex and tuple([round(mtex.tex.crop[i],3) for i in range(4)])==uv:
                    break
        else:
            tex=Texture.New(name)
            tex.type=Texture.Types.IMAGE
            tex.image=self.image
            tex.imageFlags|=Texture.ImageFlags.USEALPHA
            tex.setExtend('Clip')
            tex.crop=uv

            mat=Material.New(name)
            mat.mode|=(Material.Modes.HALO|Material.Modes.HALOTEX)
            mat.rgbCol=clampedrgba[:3]
            mat.alpha=clampedrgba[3]
            mat.haloSize=size
            mat.setTexture(0, tex)

        mesh=Mesh.New(name)
        mesh.mode &= ~(Mesh.Modes.TWOSIDED|Mesh.Modes.AUTOSMOOTH)
        mesh.mode |= Mesh.Modes.NOVNORMALSFLIP

        face=NMesh.Face()
        face.mat=0
        face.mode &= ~(Mesh.FaceModes.TEX|Mesh.FaceModes.TILES)
        face.mode |= (Mesh.FaceModes.TWOSIDE|Mesh.FaceModes.DYNAMIC)
        mesh.verts.extend([[0,0,0]])
        mesh.faces.extend([[0,0]])

        ob = Object.New("Mesh", name)
        ob.link(mesh)
        scene.objects.link(ob)
        if self.armob:
            if self.bones:
                boneloc=Vertex(self.arm.bones[self.bones[-1]].head)
                ob.setLocation(self.armob.LocX+boneloc.x+v.x,
                               self.armob.LocY+boneloc.y+v.y,
                               self.armob.LocZ+boneloc.z+v.z)
            else:	# Bone can be None if no_ref
                ob.setLocation(self.armob.LocX+v.x,
                               self.armob.LocY+v.y,
                               self.armob.LocZ+v.z)
            self.armob.makeParent([ob])
            if 'makeParentBone' in dir(self.armob):	# new in 2.43
                self.armob.makeParentBone([ob],self.bones[-1])
        else:
            cur=self.globalmatrix.translationPart()
            ob.setLocation(v.x+cur[0], v.y+cur[1], v.z+cur[2])
            r=self.globalmatrix.toEuler()
            ob.rot=((radians(r.x), radians(r.y), radians(r.z)))	# for 2.43

        if self.layer:
            ob.Layer=OBJimport.LAYER[self.layer]

        if dataref:
            ob.addProperty('name', name)
            if len(dataref)>1 and (not name in datarefs or not datarefs[name]):
                # custom or ambiguous dataref
                ob.addProperty(name, '/'.join(dataref[:-1])+'/')
        if rgba[0]!=clampedrgba[0]: ob.addProperty('R', rgba[0])
        if rgba[1]!=clampedrgba[1]: ob.addProperty('G', rgba[1])
        if rgba[2]!=clampedrgba[2]: ob.addProperty('B', rgba[2])
        if rgba[3]!=clampedrgba[3]: ob.addProperty('A', rgba[3])

        ob.getMatrix()		# force recalc in 2.43 - see Blender bug #5111
        self.nprim+=1

    #------------------------------------------------------------------------
    def addLine(self,scene,v,c):
        name="Line"
        if self.verbose>1:
            print 'Info:\tImporting Line at line %s "%s"' % (self.lineno, name)

        if self.armob:
            if self.bones:
                boneloc=Vertex(self.arm.bones[self.bones[-1]].head)
            else:	# Bone can be None if no_ref
                boneloc=Vertex(0,0,0)
            centre=boneloc-self.off[-1]
        else:
            centre=Vertex(round((v[0].x+v[1].x)/2,1),
                          round((v[0].y+v[1].y)/2,1),
                          round((v[0].z+v[1].z)/2,1))
        # Orientation
        d=Vertex(abs(v[0].x-v[1].x),abs(v[0].y-v[1].y),abs(v[0].z-v[1].z))
        if d.z>max(d.x,d.y):
            e=Vertex(self.linesemi,-self.linesemi,0)
        elif d.y>max(d.z,d.x):
            e=Vertex(-self.linesemi,0,self.linesemi)
        else:	# d.x>max(d.y,d.z):
            e=Vertex(0,self.linesemi,-self.linesemi)

        # 'Line's shouldn't be merged, so add immediately
        mesh=NMesh.New(name)
        mesh.mode &= ~(NMesh.Modes.AUTOSMOOTH|NMesh.Modes.NOVNORMALSFLIP)

        face=NMesh.Face()
        face.mat=0
        face.mode &= ~(NMesh.FaceModes.TEX|NMesh.FaceModes.TILES)
        face.mode |= (NMesh.FaceModes.TWOSIDE|NMesh.FaceModes.DYNAMIC)

        mesh.verts.append(NMesh.Vert(v[0].x-centre.x+e.x,
                                     v[0].y-centre.y+e.y,
                                     v[0].z-centre.z+e.z))
        mesh.verts.append(NMesh.Vert(v[0].x-centre.x-e.x,
                                     v[0].y-centre.y-e.y,
                                     v[0].z-centre.z-e.z))
        mesh.verts.append(NMesh.Vert(v[1].x-centre.x-e.x,
                                     v[1].y-centre.y-e.y,
                                     v[1].z-centre.z-e.z))
        mesh.verts.append(NMesh.Vert(v[1].x-centre.x+e.x,
                                     v[1].y-centre.y+e.y,
                                     v[1].z-centre.z+e.z))
        for nmv in mesh.verts:
            face.v.append(nmv)

        mat=Mat(c)
        for m in self.mats[1:]:	# skip default material
            if mat.equals(m):
                mat=m
        else:
            self.mats.append(mat)
        mesh.materials.append(mat.getBlenderMat(True))
        mesh.faces.append(face)

        ob = Object.New("Mesh", name)
        ob.link(mesh)
        if self.layer:
            ob.Layer=OBJimport.LAYER[self.layer]
        if self.armob:
            ob.setLocation(self.armob.LocX+boneloc.x,
                           self.armob.LocY+boneloc.y,
                           self.armob.LocZ+boneloc.z)
            self.armob.makeParent([ob])
            if 'makeParentBone' in dir(self.armob):	# new in 2.43
                self.armob.makeParentBone([ob],self.bones[-1])
        else:
            cur=self.globalmatrix.translationPart()
            ob.setLocation(centre.x+cur[0], centre.y+cur[1], centre.z+cur[2])
            r=self.globalmatrix.toEuler()
            ob.rot=((radians(r.x), radians(r.y), radians(r.z)))	# for 2.43

        mesh.update(1)
        scene.objects.link(ob)
        ob.getMatrix()		# force recalc in 2.43 - see Blender bug #5111
        self.nprim+=1

    #------------------------------------------------------------------------
    def addFan(self, scene, token, v, uv):
        # input v: list of co-ords, uv: corresponding list of uv points
        #	v[0] and uv[0] are common to every triangle
        if self.verbose>1:
            print 'Info:\tImporting %s at line %s' % (token, self.lineno)
        nv=len(v)

        flags=0
        if self.hard:
            flags |= Face.HARD
        if self.twoside:
            flags |= Face.TWOSIDE
        if self.flat:
            flags |= Face.FLAT
        if not self.poly:
            flags |= Face.NPOLY
        if self.panel:
            flags |= Face.PANEL
        if self.alpha:
            flags |= Face.ALPHA

        faces=[]
        for f in range(1,nv-1):
            face=Face()
            face.flags=flags

            face.addVertex(v[0])
            face.addVertex(v[f+1])
            face.addVertex(v[f])
            face.addUV(uv[0])
            face.addUV(uv[f+1])
            face.addUV(uv[f])

            faces.append(face)

        if faces:
            if self.armob:
                self.addToMesh(scene,faces,self.surface,self.deck,
                               OBJimport.LAYER[self.layer],
                               (self.armob,self.off[-1],self.bones[-1]),
                               self.mat)
            else:
                self.addToMesh(scene,faces,self.surface,self.deck,
                               OBJimport.LAYER[self.layer],
                               None, self.mat)
            self.nprim+=1

    #------------------------------------------------------------------------
    def addStrip(self, scene, token, v, uv, vorder):
        # input v: list of co-ords, uv: corresponding list of uv points
        #	vorder: order of vertices within each face

        if self.verbose>1:
            print 'Info:\tImporting %s at line %s' % (token, self.lineno)
        nv=len(v)
        assert not nv%2, 'Odd %s vertices in %s' % (nv, token)

        flags=0
        if self.hard:
            flags |= Face.HARD
        if self.twoside:
            flags |= Face.TWOSIDE
        if self.flat:
            flags |= Face.FLAT
        if not self.poly:
            flags |= Face.NPOLY
        if self.panel:
            flags |= Face.PANEL
        if self.alpha:
            flags |= Face.ALPHA

        n=len(vorder)	# 3 or 4 vertices
        faces=[]
        for f in range(2,nv,n-2):
            face=Face()
            face.flags=flags

            if n==3:
                # vorder not used
                if f%2:
                    for i in range(3):
                        face.addVertex(v[f-2+i])
                        face.addUV(uv[f-2+i])
                else:
                    for i in range(3):
                        face.addVertex(v[f-i])
                        face.addUV(uv[f-i])
            else:
                for i in range(4):
                    face.addVertex(v[f-2+vorder[i]])
                    face.addUV(uv[f-2+vorder[i]])

            # Some people use quads as tris to get round limitations in v6
            # in the way that textures are mapped to triangles. This is
            # unnecessary in v7 and screws up when we try to add the same
            # vertex twice. So manually remove extra vertices
            if face.removeDuplicateVertices() < 3:
                continue

            faces.append(face)

        if faces:
            if self.armob:
                self.addToMesh(scene,faces,self.surface,self.deck,
                               OBJimport.LAYER[self.layer],
                               (self.armob,self.off[-1],self.bones[-1]),
                               self.mat)
            else:
                self.addToMesh(scene,faces,self.surface,self.deck,
                               OBJimport.LAYER[self.layer],
                               None, self.mat)
            self.nprim+=1

    #------------------------------------------------------------------------
    def addTris(self, scene, token, a, b):
        if self.verbose>1:
            print 'Info:\tImporting %s at line %s' % (token, self.lineno)

        flags=0
        if self.hard:
            flags |= Face.HARD
        if self.twoside:
            flags |= Face.TWOSIDE
        if self.flat:
            flags |= Face.FLAT
        if not self.poly:
            flags |= Face.NPOLY
        if self.panel:
            flags |= Face.PANEL
            region=self.curregion
        else:
            region=None
        if self.alpha:
            flags |= Face.ALPHA

        facelookup={}        # detect back-to-back duplicate faces
        faces=[]
        for i in range(a,a+b,3):
            face=Face()
            # points are reversed
            (vj,uvj,n2)=self.vt[self.idx[i+2]]
            v=[vj.totuple()]
            face.addVertex(vj)
            face.addUV(uvj)
            (vj,uvj,n1)=self.vt[self.idx[i+1]]
            v.append(vj.totuple())
            face.addVertex(vj)
            face.addUV(uvj)
            (vj,uvj,n0)=self.vt[self.idx[i]]
            v.append(vj.totuple())
            face.addVertex(vj)
            face.addUV(uvj)

            face.flags=flags
            face.region=region
            if not self.flat and n0.equals(n1) and n1.equals(n2):
                # Should check that vertex normals equal plane
                # normal, but unlikely that won't be true.
                face.flags|=Face.FLAT

            # Duplicate may be rotated
            if tuple(v) in facelookup or (v[1],v[2],v[0]) in facelookup or (v[2],v[0],v[1]) in facelookup:
                # back-to-back duplicate - add existing.
                #print "dupe", face, v
                if self.armob:
                    self.addToMesh(scene,faces,self.surface,self.deck,
                                   OBJimport.LAYER[self.layer],
                                   (self.armob,self.off[-1],self.bones[-1]),
                                   self.mat, True)
                else:
                    self.addToMesh(scene,faces,self.surface,self.deck,
                                   OBJimport.LAYER[self.layer],
                                   None, self.mat, True)
                # Start new mesh
                faces=[]
                facelookup={}

            v.reverse()
            facelookup[tuple(v)]=True
            faces.append(face)

        if faces:
            if self.armob:
                self.addToMesh(scene,faces,self.surface,self.deck,
                               OBJimport.LAYER[self.layer],
                               (self.armob,self.off[-1],self.bones[-1]),
                               self.mat, True)
            else:
                self.addToMesh(scene,faces,self.surface,self.deck,
                               OBJimport.LAYER[self.layer],
                               None, self.mat, True)
        self.nprim+=b/3

    #------------------------------------------------------------------------
    # add faces to existing or new mesh
    def addToMesh (self,scene,faces,surface,deck,layers,anim,mat,makenewmesh=False):
        # New faces are added to the existing mesh if existing and new faces
        # have the same flags.
        if self.curmesh:
            curmesh=self.curmesh[-1]
            if (self.merge>=2 or
                (not makenewmesh and
                 curmesh.layers==layers and
                 (curmesh.surface==surface or curmesh.surface==None or surface==None) and
                 (curmesh.deck==deck or curmesh.deck==None or deck==None) and
                 curmesh.anim==anim and
                 curmesh.mat==mat and
                 not curmesh.isduplicate(faces))):
                curmesh.addFaces(faces)
                if surface: curmesh.surface=surface
                if deck!=None: curmesh.deck=deck
                return

        # new mesh required
        self.curmesh.append(MyMesh(faces, surface, deck, layers, anim, mat))

    #------------------------------------------------------------------------
    def addpendingbone(self):
        if not self.pendingbone:
            if self.bones==[None]:
                # eek no bones! Maybe just receptacle for show/hide?
                (origname, head, tail)=('Bone', Vertex(0,0,0), Vertex(0,0.1,0))
                m=[Matrix().identity().resize4x4()]
            else:
                return None
        else:
            (origname, head, tail, m)=self.pendingbone
        name=make_short_name(origname)
        i=0
        while name in self.arm.bones.keys():
            i+=1
            name=make_short_name("%s.%03d" % (origname, i))
        bone=Armature.Editbone()
        bone.name=name
        i=len(self.bones)-2
        while i>=0:
            if self.bones[-2]:
                bone.parent=self.arm.bones[self.bones[-2]]
                break
            i-=1	# bone will be None if just a shift - use grandparent
        bone.head=head.toVector(3)
        bone.tail=tail.toVector(3)
        self.arm.bones[name]=bone
        self.arm.update()	# to get Pose
        pose=self.armob.getPose()
        posebone=pose.bones[name]
        for i in range(len(m)):
            posebone.localMatrix=m[i]
            posebone.insertKey(self.armob, i+1, [Object.Pose.ROT,Object.Pose.LOC])
            pose.update()
        self.arm.makeEditable()
        self.pendingbone=None
        self.bones[-1]=name

    #------------------------------------------------------------------------
    def addArmProperty(self, name, value):
        for prop in self.armob.getAllProperties():
            if prop.name==name:
                if prop.data==value:
                    return False
                else:
                    prop.data=value
                    return True
        self.armob.addProperty(name, value)
        return True

    #------------------------------------------------------------------------
    def getpanel(self):
        if self.panelimage: return
        d=dirname(self.filename)
        for c in listdir(d):
            if c.lower()=='cockpit':
                for p in listdir(join(d,c)):
                    if p.lower()=='-panels-':
                        for ext in ['.dds','.png','.bmp']:
                            for tex in listdir(join(d,c,p)):
                                if tex.lower()=='panel'+ext:
                                    try:
                                        self.panelimage=Image.Load(join(d,c,p,tex))
                                        self.panelimage.getSize()	# force load
                                        break
                                    except:
                                        pass
                        break
                break
        if not self.panelimage:
            raise ParseError(ParseError.PANEL)
