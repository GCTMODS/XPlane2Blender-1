@echo off

set FILES=helpXPlane.py uvCopyPaste.py uvFixupACF.py uvResize.py XPlaneExport.py XPlaneExport7.py XPlaneExport8.py XPlaneExportCSL.py XPlaneImport.py XPlaneImportPlane.py XPlaneUtils.py XPlane2Blender.html DataRefs.txt

if exist XPlane2Blender.zip del XPlane2Blender.zip
zip -9 XPlane2Blender.zip install.cmd install.command %FILES%