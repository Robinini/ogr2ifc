#!/usr/bin/python3

"""
Script and classes to convert an ogc supported vector format file to an IFC file
"""

import os
import argparse
import time
import logging
import ogr
import ifcopenshell
from shapely.affinity import translate, rotate
from shapely.geometry import Point
from ifcopenshell.template import TEMPLATE, create, DEFAULTS

# ToDO: Curve geometry
# ToDO: Line/Point geometry
# ToDo: Solid support of recursive geometry types

# ToDo: Directory convert version
"""

Point, Multipoint,  Line, Multiline, 
 Polygon ring, Polygon, Multipolygon, Geometry collection
 Compound* *Curve, 'COMPOUNDCURVE'...

"""

# ToDO: Spaces instead of building (layer space composed of feature spaces aggregated)

# ToDo: Support 3D data - if top_elevation but not bottom, use 3D as bottom (and reverse for bottom_elevation)
# https://standards.buildingsmart.org/IFC/DEV/IFC4_3/RC1/HTML/schema/ifcrepresentationresource/lexical/ifcshaperepresentation.htm

# ToDo Comments/Documentation


####################################################################################
# Coordinate Transformation function generators
# Can be supplied to Ogr2Ifc as coord_transformer parameter.
# Creates function to convert shapely geometry to IFC coordinate space
# See https://shapely.readthedocs.io/en/stable/manual.html for other options

def transformer(eastings=0.0, northings=0.0, orthogonal_height=0.0, rotation=0):
    """

    :param eastings: Specifies the location along the easting of the coordinate system of the
    target map coordinate reference system.
    :param northings: Specifies the location along the northing of the coordinate system of the
    target map coordinate reference system.
    :param orthogonal_height: Orthogonal height relative to the vertical datum specified
    :param rotation: degrees (positive angles are counter-clockwise)
    :return: function to convert shapely geometry to IFC coordinate space
    """

    def coord_transformer(geom):
        geom = translate(geom, xoff=-eastings, yoff=-northings, zoff=-orthogonal_height)
        return rotate(geom, angle=rotation, origin=(0, 0))

    return coord_transformer


####################################################################################
# Generate guid
create_guid = ifcopenshell.guid.new

####################################################################################
# Standard Vertices and Vectors
null = 0., 0., 0.
X = 1., 0., 0.
Y = 0., 1., 0.
Z = 0., 0., 1.


####################################################################################
# Placement

# Creates an IfcAxis2Placement3D from Location, Axis and RefDirection specified as Python tuples
def create_ifcaxis2placement(ifcfile, point=null, dir1=Z, dir2=X):
    point = ifcfile.createIfcCartesianPoint(point)
    dir1 = ifcfile.createIfcDirection(dir1)
    dir2 = ifcfile.createIfcDirection(dir2)
    axis2placement = ifcfile.createIfcAxis2Placement3D(point, dir1, dir2)
    return axis2placement


# Creates an IfcLocalPlacement from Location, Axis and RefDirection, specified as Python tuples, and relative placement
def create_ifclocalplacement(ifcfile, point=null, dir1=Z, dir2=X, relative_to=None):
    axis2placement = create_ifcaxis2placement(ifcfile, point, dir1, dir2)
    ifclocalplacement2 = ifcfile.createIfcLocalPlacement(relative_to, axis2placement)
    return ifclocalplacement2


####################################################################################
# Classes

class Ogr2Ifc:
    def __init__(self, gis_file_path=None, top_elevation=10000.0, bottom_elevation=0.0,
                 coord_transformer=None, transform_elevations=True):
        """

        :param gis_file_path: Path to ogr supported vector GIS file
        :param top_elevation: Upper elevation of extruded volume. If text, GIS attribute value will be used,
        or self.max_elevation if NULL or not available
        :param bottom_elevation: Lower elevation of extruded volume. If text, GIS attribute value will be used,
        or self.min_elevation if NULL or not available
        :param coord_transformer: Function to convert shapely geometry to IFC coordinate space

        """

        # Shape representations to create
        self.CoG = False
        self.Box = False
        self.Axis = True
        self.FootPrint = False
        self.Surface = True
        self.Body = True

        self.top_elevation = top_elevation if top_elevation is not None else 10000.0  # default maximum
        self.bottom_elevation = bottom_elevation if bottom_elevation is not None else 0.0  # default min

        self.coord_transformer = coord_transformer if coord_transformer else transformer
        self.ifcfile = self.create_ifc()

        self.dataSource = None
        if gis_file_path:
            self.load_gis_file(gis_file_path)


    def load_gis_file(self, gis_file_path):
        if not os.path.isfile(gis_file_path):
            raise FileNotFoundError(f'File {gis_file_path} not found')
        self.dataSource = ogr.Open(gis_file_path)

    def create_ifc(self):

        ############################################
        # IFC template creation
        settings = DEFAULTS
        #settings['filename'] = os.path.basename(self.bim_file_path)
        settings['timestamp'] = time.time()
        settings['timestring'] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time()))
        settings['creator'] = "Robin Dainton"
        settings['organization'] = "Dainton Inc."
        settings['application'] = "IfcOpenShell"
        settings['application_version'] = "0.5"
        settings['schema_identifier'] = "IFC4"
        settings['project_globalid'] = create_guid()
        settings['project_name'] = "GIS2BIM"

        # Create new file from template
        ifcfile = create(**settings)

        # Obtain references to instances defined in template, for use in construction
        self.owner_history = ifcfile.by_type("IfcOwnerHistory")[0]
        self.project = ifcfile.by_type("IfcProject")[0]
        self.context = ifcfile.by_type("IfcGeometricRepresentationContext")[0]

        ############################################
        # IFC hierarchy creation
        self.site_placement = create_ifclocalplacement(ifcfile)
        self.site = ifcfile.createIfcSite(create_guid(), self.owner_history, "Site", None, None,
                                               self.site_placement, None, None, "ELEMENT",
                                               None, None, None, None, None)


        self.building_placement = create_ifclocalplacement(ifcfile, relative_to=self.site_placement)
        self.building = ifcfile.createIfcBuilding(create_guid(), self.owner_history, 'GIS2BIM',
                                                       None, None, self.building_placement, None, None,
                                                       "ELEMENT", None, None, None)

        self.container_site = ifcfile.createIfcRelAggregates(create_guid(), self.owner_history, "Site Container",
                                                                  None, self.site, [self.building])
        self.container_project = ifcfile.createIfcRelAggregates(create_guid(), self.owner_history,
                                                                     "Project Container", None, self.project,
                                                                     [self.site])

        return ifcfile

    def create_storey(self, name):
        self.storey_placement = create_ifclocalplacement(self.ifcfile, relative_to=self.building_placement)
        self.building_storey = self.ifcfile.createIfcBuildingStorey(create_guid(), self.owner_history,
                                                               name, None, None, self.storey_placement,
                                                               None, None, "ELEMENT", 0)

        storey = self.ifcfile.createIfcRelAggregates(create_guid(), self.owner_history,
                                                               "Building Container", None, self.building,
                                                               [self.building_storey])
        return storey

    def save_ifc(self, bim_file_path=None):
        # Save ifc file
        os.makedirs(os.path.dirname(bim_file_path), exist_ok=True)
        self.ifcfile.write(bim_file_path)
        print(f'IFC file written to {bim_file_path}')

    def add_vector_layers(self, layernames=None):

        if isinstance(layernames, str):
            layernames = [layernames]

        for layer in self.dataSource:
            if layernames is None or layer.GetName() in layernames:
                # Add features
                self.add_layer_objects(layer)

    def add_property_set(self, layer, feature, ifc_element):
        layername = layer.GetName()

        # Create and assign property set
        attributes = feature.items()
        property_values = list()

        for k, v in attributes.items():
            if isinstance(v, bool):
                property_values.append(
                    self.ifcfile.createIfcPropertySingleValue(k, k, self.ifcfile.create_entity("IfcBoolean", v), None))
            elif isinstance(v, int):
                property_values.append(
                    self.ifcfile.createIfcPropertySingleValue(k, k, self.ifcfile.create_entity("IfcInteger", v), None))
            elif isinstance(v, float):
                property_values.append(
                    self.ifcfile.createIfcPropertySingleValue(k, k, self.ifcfile.create_entity("IfcReal", v), None))
            # toDo: Dates etc...
            else:
                property_values.append(
                    self.ifcfile.createIfcPropertySingleValue(k, k,
                                                              self.ifcfile.create_entity("IfcText", str(v)), None))

        property_set = self.ifcfile.createIfcPropertySet(create_guid(), self.owner_history,
                                                         "ePset_GIS2BIM_%s" % layername, None, property_values)
        self.ifcfile.createIfcRelDefinesByProperties(create_guid(), self.owner_history, None, None, [ifc_element],
                                                     property_set)

    def add_layer_objects(self, layer):
        layername = layer.GetName()

        # Add parent space
        space = self.ifcfile.createIfcSpace(GlobalId=create_guid(), Description='GIS2 Bim Layer space', OwnerHistory=self.owner_history,
                                            Name=layername, ObjectPlacement=self.site_placement)

        space = self.create_storey(layer.GetName())

        for feature in layer:
            self.add_feature(layer, space, feature)

    def add_feature(self, layer, space, feature):

        ############################################
        # Wall creation: Define the ifc_element shape as a polyline axis and an extruded area solid
        layername = layer.GetName()

        feature_placement = create_ifclocalplacement(self.ifcfile)  #, relative_to=self.storey_placement)

        shape = Ogr2Shape(self, feature)

        product_shape = self.ifcfile.createIfcProductDefinitionShape(None, None, shape.representations())

        ifc_element = self.ifcfile.createIfcWallStandardCase(create_guid(), self.owner_history,
                                                             'GIS2BIM Layer %s, Feature ID %s' % (layername,
                                                                                               feature.GetFID()),
                                                             "A GIS2BIM ifc_element",
                                                             None, feature_placement, product_shape, None)

        self.ifcfile.createIfcRelAggregates(create_guid(), self.owner_history,
                                                         "Feature space", None, space,
                                                         [ifc_element])

        # Add property information
        self.add_property_set(layer, feature, ifc_element)

        # Add quantity information
        feature_quantities = self.feature_quantities(feature)
        if feature_quantities:
            element_quantity = self.ifcfile.createIfcElementQuantity(create_guid(), self.owner_history, "BaseQuantities",
                                                                     None, None, feature_quantities)
            self.ifcfile.createIfcRelDefinesByProperties(create_guid(), self.owner_history, None, None, [ifc_element],
                                                         element_quantity)


        # Relate the ifc_element to the building storey
        self.ifcfile.createIfcRelContainedInSpatialStructure(create_guid(), self.owner_history,
                                                             "Building Storey Container", None, [ifc_element],
                                                             self.building_storey)
    def feature_quantities(self, feature):
        geomref = feature.GetGeometryRef()
        if geomref.GetGeometryName().upper() in ('POLYGON', 'MULTIPOLYGON'):
            return [self.ifcfile.createIfcQuantityArea("Area", "Area of the GIS feature", None, geomref.Area())]
        elif geomref.GetGeometryName().upper() in ('LINE', 'MULTILINE'):
            return [self.ifcfile.createIfcQuantityArea("Length", "Length of the GIS feature", None, geomref.Length())]


class Ogr2Shape:
    def __init__(self, ogr2ifc, feature):
        self.ogr2ifc = ogr2ifc
        self.feature = feature

    def geom_type(self, *types):
        return self.feature.GetGeometryRef().GetGeometryName().upper() \
               in list([type.upper() for type in types])

    def representations(self):

        shapes = []
        if self.ogr2ifc.CoG:
            shapes += self.cog()
        if self.ogr2ifc.Box:
            shapes += self.box()
        if self.ogr2ifc.Axis:
            shapes += self.axis()
        if self.ogr2ifc.FootPrint:
            shapes += self.footprint()
        if self.ogr2ifc.Surface:
            shapes += self.surface()
        if self.ogr2ifc.Body:
            shapes += self.body()

        return shapes

    def extrusion_bounds(self):
        # Obtain extrusion limits of feature (top_elevation, bottom_elevation)
        if isinstance(self.ogr2ifc.bottom_elevation, str):
            bottom_elevation = self.feature.items().get(self.ogr2ifc.bottom_elevation)
            if bottom_elevation is None:
                logging.info('Bottom elevation for feature %s set to min' % self.feature.GetFID())
                bottom_elevation = self.ogr2ifc.min_elevation
        else:
            bottom_elevation = self.ogr2ifc.bottom_elevation

        if isinstance(self.ogr2ifc.top_elevation, str):
            top_elevation = self.feature.items().get(self.ogr2ifc.top_elevation)
            if top_elevation is None:
                logging.info('Top elevation for feature %s set to max' % self.feature.GetFID())
                top_elevation = self.ogr2ifc.max_elevation
        else:
            top_elevation = self.ogr2ifc.top_elevation

        # Ensure that values are numerical
        top_elevation, bottom_elevation = float(top_elevation), float(bottom_elevation)

        return top_elevation, bottom_elevation

    def cog(self):
        raise NotImplementedError

    def box(self):
        raise NotImplementedError

    def axis(self):
        # Todo - this is rough test
        axes = list()

        if not self.geom_type('Point', 'Multipoint'):
            return []

        top_elevation, bottom_elevation = self.extrusion_bounds()

        geomref = self.feature.GetGeometryRef()  # Object

        if geomref.GetGeometryCount() > 1:
            raise('Multi points not supported')

        point = geomref.GetPoint()
        axes.append(self.create_ifcpolyline([(point[0], point[1], bottom_elevation),
                                             (point[0], point[1], top_elevation)], dimensions=3))

        return [self.ogr2ifc.ifcfile.createIfcShapeRepresentation(self.ogr2ifc.context, "Axis", "Curve2D", axes)]

    def footprint(self):
        raise NotImplementedError

    def surface(self):
        if not self.geom_type('Linestring', 'Multilinestring'):
            return []

        top_elevation, bottom_elevation = self.extrusion_bounds()
        geomref = self.feature.GetGeometryRef()

        if self.geom_type('Multilinestring'):
            raise NotImplementedError  # for i in range(geomref.GetGeometryCount()):

        segment_points = [geomref.GetPoint(i) for i in range(geomref.GetPointCount())]
        points_lists = list()
        for i in range(1, len(segment_points)):
            points_lists.append([list(segment_points[i-1][:2])+[bottom_elevation],
                                 list(segment_points[i][:2])+[bottom_elevation],
                                 list(segment_points[i][:2])+[top_elevation],
                                 list(segment_points[i-1][:2])+[top_elevation],
                                 list(segment_points[i-1][:2])+[bottom_elevation]])

        #points_lists.append([segment.GetPoint(i) for i in range(segment.GetPointCount())])

        faces = self.create_ifcfaces(points_lists)
        return [self.ogr2ifc.ifcfile.createIfcShapeRepresentation(self.ogr2ifc.context, "Surface", "Surface", faces)]

    def body(self):

        if not self.geom_type('Polygon', 'Multipolygon'):
            return []

        top_elevation, bottom_elevation = self.extrusion_bounds()
        extrusion_distance = top_elevation - bottom_elevation

        # Transform values
        bottom_elevation_transformed = self.ogr2ifc.coord_transformer(Point(0, 0, bottom_elevation)).z
        extrusion_placement = create_ifcaxis2placement(self.ogr2ifc.ifcfile, (0.0, 0.0, bottom_elevation_transformed), Z, X)
        solids = self.create_ifcextrudedareasolids(extrusion_placement, Z, extrusion_distance)

        return [self.ogr2ifc.ifcfile.createIfcShapeRepresentation(self.ogr2ifc.context, "Body", "SweptSolid", solids)]

    ####################################################################################
    # IFC Geometry
    # https://standards.buildingsmart.org/IFC/DEV/IFC4_3/RC1/HTML/schema/ifcrepresentationresource/lexical/ifcshaperepresentation.htm

    # Point
    def create_ifcpoints(self, points, dimensions=2):
        return [self.create_ifcpoint(point, dimensions) for point in points]

    def create_ifcpoint(self, point, dimensions=2):
        point = self.ogr2ifc.coord_transformer(Point(*point)).coords[0]
        return self.ogr2ifc.ifcfile.createIfcCartesianPoint(point[:dimensions])

    # Line
    def create_ifcpolyline(self, point_list, dimensions=2):
        return self.ogr2ifc.ifcfile.createIfcPolyLine(self.create_ifcpoints(point_list, dimensions))

    # Face
    def create_ifcfaces(self, points_lists, dimensions=3):
        return [self.create_ifcface(points_list, dimensions) for points_list in points_lists]

    def create_ifcface(self, points_list, dimensions=3):
        points = self.create_ifcpoints(points_list, dimensions)
        polyloop = self.ogr2ifc.ifcfile.createIfcPolyLoop(points)
        outer_bounds = self.ogr2ifc.ifcfile.createIfcFaceBound(polyloop)
        return self.ogr2ifc.ifcfile.createIfcFaceSurface([outer_bounds])

    # Body
    def create_ifcextrudedareasolids(self, ifcaxis2placement, extrude_dir, extrusion):
        """
        Supports multigeometry. Returns list of extruded solids (if single geometry, list of length one)

        :param ifcaxis2placement:
        :param extrude_dir:
        :param extrusion:
        :return:
        """

        geomref = self.feature.GetGeometryRef()  # Object

        if self.geom_type('Multipolygon'):
            return [self.create_ifcextrudedareasolid(geomref.GetGeometryRef(i),
                                                     ifcaxis2placement, extrude_dir, extrusion)
                for i in range(geomref.GetGeometryCount())]
        else:
            return [self.create_ifcextrudedareasolid(geomref, ifcaxis2placement, extrude_dir, extrusion)]

    def create_ifcextrudedareasolid(self, geomref, ifcaxis2placement, extrude_dir, extrusion):
        """
        Creates an createIfcArbitraryClosedProfileDef or IfcArbitraryProfileDefWithVoids from an ogc polygon feature

        :param geomref:
        :param ifcaxis2placement:
        :param extrude_dir:
        :param extrusion:
        :return:
        """
        geomcount = geomref.GetGeometryCount()

        # Outer ring
        outer_ring = geomref.GetGeometryRef(0)
        point_list = [outer_ring.GetPoint(i) for i in range(outer_ring.GetPointCount())]
        outer_polyline = self.create_ifcpolyline(point_list)

        # Create profile
        if geomcount == 1:  # Simple profile
            ifc_profile = self.ogr2ifc.ifcfile.createIfcArbitraryClosedProfileDef("AREA", None, outer_polyline)
        else:  # Has inner voids/holes
            # Inner bounds
            inner_polylines = []
            for j in range(1, geomcount):
                inner_ring = geomref.GetGeometryRef(j)
                point_list = [inner_ring.GetPoint(i) for i in range(inner_ring.GetPointCount())]
                inner_polylines.append(self.create_ifcpolyline(point_list))

            # IfcArbitraryProfileDefWithVoids
            ifc_profile = self.ogr2ifc.ifcfile.createIfcArbitraryProfileDefWithVoids("AREA", None, outer_polyline, inner_polylines)

        # Extrude profile to solid
        ifcdir = self.ogr2ifc.ifcfile.createIfcDirection(extrude_dir)
        ifcextrudedareasolid = self.ogr2ifc.ifcfile.createIfcExtrudedAreaSolid(ifc_profile, ifcaxis2placement, ifcdir, extrusion)
        return ifcextrudedareasolid


if __name__ == '__main__':

    # Command line operation
    # ToDo: Add coord trans values

    parser = argparse.ArgumentParser(description='Convert an ogc supported vector format file to an IFC file')
    parser.add_argument('dst_ifc_file', help='destination IFC file to be created')

    parser.add_argument('-top', help='Upper elevation for extruded IFC shape representations. '
                                     'If text, GIS attribute value will be used')
    parser.add_argument('-bottom', help='Lower elevation for extruded IFC shape representations. '
                                        'If text, GIS attribute value will be used')

    parser.add_argument('src_gis_file', help='source GIS vector file to be converted')
    parser.add_argument('layername', nargs='?', help='layername to be converted. '
                                                     'If not provided, all layers will be converted')

    # Get user arguments
    args = parser.parse_args()

    # Recast top/bottom elevations to floats if possible
    try:
        args.top = float(args.top)
    except:
        pass  # Assume this is an attribute name
    try:
        args.bottom = float(args.bottom)
    except:
        pass  # Assume this is an attribute name

    o2i = Ogr2Ifc(gis_file_path=args.src_gis_file, top_elevation=args.top, bottom_elevation=args.bottom)

    o2i.add_vector_layers(args.layername)
    o2i.save_ifc(args.dst_ifc_file)
