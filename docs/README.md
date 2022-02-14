# ogr2ifc
ogr2ifc converts GIS data to BIM models using GDAL/OGR (read) 
and IfcOpenShell-python (write).

This allows the import or visualisation of GIS data in a BIM project.

All GIS [vector data formats supported by GDAL/OGR](https://gdal.org/drivers/vector/index.html) can be converted.

GIS features are converted to `IfcProduct`/`IfcWall` elements. 
GIS attributes are also added to the IFC element as custom property sets.

GIS geometries can be converted to multiple 
[IfcShapeRepresentations](https://standards.buildingsmart.org/IFC/DEV/IFC4_3/RC1/HTML/schema/ifcrepresentationresource/lexical/ifcshaperepresentation.htm).

Coordinates can be transformed to match the BIM project coordinate system using simple transformation and rotation, or a 
custom coordinate transformation can be applied by passing a transformation function.

Depending on the representation geometry created, GIS geometries are extruded vertically to produce lines, surfaces or volumes.
Extrusion boundaries can be defined using fixed elevations, or using attribute values from each GIS feature 
(eg: `floor-slab_elevation` and `roof_apex`) data attributes.

# Development Status
This tool is currently in development.

### Implemented
* Polygon implemented (swept solid extrusion)
  * Inner holes supported
  * Multipolygons supported
* Attributes added as custom property set
* Coordinate transformation
  
### Under Development
* Points, lines, footprints
* Curved geometry
* Surfaces
* Create features as part of `IfcSpace` instead of `IfcBuilding`
* use of IFC4 `HasCoordinateOperation`/`IfcMapConversion` as alternative to transformation

# Installation
Dependencies:
* Python 3
  * [ifcopenshell-python](http://ifcopenshell.org/python)
  * [GDAL](https://pypi.org/project/GDAL/)
  * [shapely](https://shapely.readthedocs.io/en/stable/manual.html)

Copy file `ogr2ifc.py` to the script folder or to a folder on the python module search path. 

# Command Line Use
See `python ogr2ifc.py -h` for command line use.

Example use in command line:
```
python ogr2ifc.py gis2bim.ifc polygons.shp -top 520 -bottom 450
```

# Python Module
The python classes offer more flexibility and functionality, including coordinate transformations.
See the main conversion class `Ogr2Ifc` for details.

Example use in python scripts:
```python
o2i = Ogr2Ifc('gis_files/complex.gpkg', bottom_elevation='bottom', top_elevation='top')
o2i.add_vector_layers('multipolies')
o2i.save_ifc('test.ifc')
```

# Geometry Representations
Multiple [IfcShapeRepresentations](https://standards.buildingsmart.org/IFC/DEV/IFC4_3/RC1/HTML/schema/ifcrepresentationresource/lexical/ifcshaperepresentation.htm).
 can be created for each feature.

Prior to conversion, the Ogr2Ifc instance attributes below can be modified to 
create the desired representations:

<table>
  <tr>
    <th rowspan="2">Ogr2Ifc Attribute / IFC Identifier</th>
    <th rowspan="2">Description</th>
    <th colspan="4">Implemented for <a href="https://gdal.org/doxygen/classOGRGeometry.html">OGRGeometry Class</a></th>
  </tr>
  <tr><th>Point</th><th>Line</th><th>Polygon</th><th>Triangle/Polyhedral/TIN</th></tr>
  <tr>
    <td><code>CoG</code></td>
    <td>Center of gravity<br>3D <em>IfcCartesianPoint</em></td>
    <td>(Y)</td><td>(Y)</td><td>(Y)</td><td>&nbsp;</td>
  </tr>
  <tr>
    <td><code>Box</code></td>
    <td>Bounding box</td>
  <td>&nbsp;</td><td>&nbsp;</td><td>(Y*)</td><td>&nbsp;</td>
  </tr>
  <tr>
    <td><code>Axis</code></td>
    <td>Line representation of an element</td>
  <td>(Y*)</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>
  </tr>
  <tr>
    <td><code>FootPrint</code></td>
    <td>Foot print projected to ground view</td>
  <td>&nbsp;</td><td>&nbsp;</td><td>(Y)</td><td>&nbsp;</td>
  </tr> 
  <tr>
    <td><code>Surface</code></td>
    <td>3D Surface representation</td>
  <td>&nbsp;</td><td>(Y*)</td><td>&nbsp;</td><td>(Y)</td>
  </tr> 
  <tr>
    <td><code>Body</code></td>
    <td>3D Body representation</td>
  <td>&nbsp;</td><td>&nbsp;</td><td>Y*</td><td>&nbsp;</td>
  </tr>
  <tr>
    <td colspan="6">
      * Extruded to elevation bounds<br>
      (Y) planned functionality
    </td>
  </tr>
</table>


For example:

```python
o2i = Ogr2Ifc('gis_files/complex.gpkg')
o2i.Box = True
...
```

# Transformation
To convert coordinates from a GIS `WorldCoordinateSystem`
to the IFC project coordinate system, a function can be 
created and passed to the converter as follows:

```python
from ogr2ifc import Ogr2Ifc, transformer

# Create coordinate transformation function
coord_tran = transformer(eastings=2719310, northings=1225070, 
                         orthogonal_height=410.10, rotation=44.2939)

# Convert
o2i = Ogr2Ifc('gis_files/poly.shp', coord_transformer=coord_tran)
```

Custom transformations can also be provided, for example
any [shapely transformation](https://shapely.readthedocs.io/en/stable/manual.html#affine-transformations), including
[map reprojections](https://shapely.readthedocs.io/en/stable/manual.html#other-transformations).

# Example Visualisation

### GIS File
![GIS File Source](GIS_file.png?raw=true)
### BIM IFC File
![IFC File](example_ifc.png?raw=true)