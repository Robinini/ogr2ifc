# ogr2ifc
GIS to BIM conversion using GDAL/OGR and IfcOpenShell-python.

Allows the import of GIS data into a BIM Project.

X, Y values from Easting and Nothing values in GIS data.
Upper and lower extrusion boundaries (Z) either fixed or from GIS data attributes.

Proof of concept (previously converted to DWG then manually modified in Revit).

*Warning*: In developement. This is my first experience with IFC/BIM and is a learning project and should be treated as such

# Useage
See `python ogr2ifc.py -h` for command line useage.

Example use in python scripts:
```python
Ogr2Ifc('gis_files/complex.gpkg', file_path, bottom_elevation='bottom', top_elevation='top')
```

# Status
* Polygon implemented (swept solid extrusion)
  * Inner holes supported
  * Multipolygons supported
  * Curves not supported
* Attributes added as property set
  
* Points, lines not yet supported
* relate to IfcSpace, not IfcBuilding (currently)

# GIS
![GIS File Source](GIS_file.png?raw=true)
# BIM
![IFC File](example_ifc.png?raw=true)