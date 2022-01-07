#!/usr/bin/python3

"""
Script and classes to convert an ogc supported vector format file to an IFC file
"""

import os
import argparse
import uuid
import time
import logging
import ogr
import ifcopenshell
from ifcopenshell.template import TEMPLATE, create, DEFAULTS

# ToDO: Curve geometry
# ToDO: Line/Point geometry
# ToDo: Solid support of recursive geometry types
# ToDO: Space instead of building
# ToDO: Attributes - ok?
# ToDo: Make OO provide ability to do individual layers and objects
# ToDo: Command line version with arguments

# Idea for 3D data - if top_elevation but not bottom, use 3D as bottom (and reverse for bottom_elevation)

####################################################################################
# IFC
####################################################################################

####################################################################################
# Generate guid
create_guid = lambda: ifcopenshell.guid.compress(uuid.uuid1().hex)

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
    def __init__(self, gis_file_path, bim_file_path, top_elevation=10000.0, bottom_elevation=0.0):
        """

        :param gis_file_path: Path to ogr supported vector GIS file
        :param bim_file_path: Path to save IFC file
        :param top_elevation: Upper elevation of extruded volume. If text, GIS attribute value will be used,
        or self.max_elevation if NULL or not available
        :param bottom_elevation: Lower elevation of extruded volume. If text, GIS attribute value will be used,
        or self.min_elevation if NULL or not available
        """

        # Shape representations, typically *increasing th dimensionality of the features
        # https://standards.buildingsmart.org/IFC/DEV/IFC4_3/RC1/HTML/schema/ifcrepresentationresource/lexical/ifcshaperepresentation.htm
        self.CoG = False
        self.Box = False
        self.Axis = False
        self.FootPrint = False
        self.Surface = True
        self.Body = True

        self.max_elevation = 10000.0  # default maximum extruded elevation
        self.min_elevation = 0.0  # default minimum extruded elevation
        self.top_elevation = top_elevation if top_elevation is not None else self.max_elevation
        self.bottom_elevation = bottom_elevation if bottom_elevation is not None else self.min_elevation

        ############################################
        # IFC template creation
        settings = DEFAULTS
        settings['filename'] = os.path.basename(bim_file_path)
        settings['timestamp'] = time.time()
        settings['timestring'] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time()))
        settings['creator'] = "Robin Dainton"
        settings['organization'] = "HBT"
        settings['application'] = "IfcOpenShell"
        settings['application_version'] = "0.5"
        settings['schema_identifier'] = "IFC4"
        settings['project_globalid'] = create_guid()
        settings['project_name'] = "GIS2BIM"

        # Create new file from template
        self.ifcfile = create(**settings)

        # Obtain references to instances defined in template, for use in construction
        self.owner_history = self.ifcfile.by_type("IfcOwnerHistory")[0]
        self.project = self.ifcfile.by_type("IfcProject")[0]
        self.context = self.ifcfile.by_type("IfcGeometricRepresentationContext")[0]

        ############################################
        # IFC hierarchy creation
        self.site_placement = create_ifclocalplacement(self.ifcfile)
        self.site = self.ifcfile.createIfcSite(create_guid(), self.owner_history, "Site", None, None,
                                               self.site_placement, None, None, "ELEMENT",
                                               None, None, None, None, None)

        self.building_placement = create_ifclocalplacement(self.ifcfile, relative_to=self.site_placement)
        self.building = self.ifcfile.createIfcBuilding(create_guid(), self.owner_history, 'Building',
                                                       None, None, self.building_placement, None, None,
                                                       "ELEMENT", None, None, None)

        self.storey_placement = create_ifclocalplacement(self.ifcfile, relative_to=self.building_placement)
        self.building_storey = self.ifcfile.createIfcBuildingStorey(create_guid(), self.owner_history,
                                                                    'Storey', None, None, self.storey_placement,
                                                                    None, None, "ELEMENT", 0)

        self.container_storey = self.ifcfile.createIfcRelAggregates(create_guid(), self.owner_history,
                                                                    "Building Container", None, self.building,
                                                                    [self.building_storey])
        self.container_site = self.ifcfile.createIfcRelAggregates(create_guid(), self.owner_history, "Site Container",
                                                                  None, self.site, [self.building])
        self.container_project = self.ifcfile.createIfcRelAggregates(create_guid(), self.owner_history,
                                                                     "Project Container", None, self.project,
                                                                     [self.site])

        # Add GIS data
        if not os.path.isfile(gis_file_path):
            raise FileNotFoundError(f'File {gis_file_path} not found')
        self.dataSource = ogr.Open(gis_file_path)
        self.add_vector_layers()

        # Save ifc file
        os.makedirs(os.path.dirname(bim_file_path), exist_ok=True)
        self.ifcfile.write(bim_file_path)
        print(f'IFC file written to {bim_file_path}')

    def __del__(self):
        try:
            self.dataSource.Destroy()
        except AttributeError:
            pass

    def add_vector_layers(self):
        for layer in self.dataSource:
            # Add features
            self.add_layer_objects(layer)

    def add_layer_property_set(self, layer, feature, ifc_element):
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
                    self.ifcfile.createIfcPropertySingleValue(k, k, self.ifcfile.create_entity("IntValue", v), None))
            elif isinstance(v, float):
                property_values.append(
                    self.ifcfile.createIfcPropertySingleValue(k, k, self.ifcfile.create_entity("IfcReal", v), None))
            # toDo: Dates etc...
            else:
                property_values.append(
                    self.ifcfile.createIfcPropertySingleValue(k, k,
                                                              self.ifcfile.create_entity("IfcText", str(v)), None))

        property_set = self.ifcfile.createIfcPropertySet(create_guid(), self.owner_history,
                                                         "Pset_GIS2BIM_%s" % layername, None, property_values)
        self.ifcfile.createIfcRelDefinesByProperties(create_guid(), self.owner_history, None, None, [ifc_element],
                                                     property_set)

    def add_layer_objects(self, layer):
        layername = layer.GetName()

        # Add parent space
        space = self.ifcfile.createIfcSpace(create_guid(), self.owner_history, layername)

        for feature in layer:
            self.add_feature(layer, space, feature)

    def add_feature(self, layer, space, feature):

        ############################################
        # Wall creation: Define the ifc_element shape as a polyline axis and an extruded area solid
        layername = layer.GetName()

        feature_placement = create_ifclocalplacement(self.ifcfile, relative_to=self.storey_placement)

        shape = Ogr2Shape(self, feature)

        product_shape = self.ifcfile.createIfcProductDefinitionShape(None, None, shape.representations())

        ifc_element = self.ifcfile.createIfcWallStandardCase(create_guid(), self.owner_history,
                                                             'GIS2BIM Layer %s, Feature ID %s' % (layername,
                                                                                               feature.GetFID()),
                                                             "A GIS2BIM ifc_element",
                                                             None, feature_placement, product_shape, None)

        # Add property information
        self.add_layer_property_set(layer, feature, ifc_element)

        # Add quantity information
        geomref = feature.GetGeometryRef()
        quantity_values = [self.ifcfile.createIfcQuantityArea("Area", "Area of the GIS feature", None, geomref.Area())]
        element_quantity = self.ifcfile.createIfcElementQuantity(create_guid(), self.owner_history, "BaseQuantities",
                                                                 None, None, quantity_values)
        self.ifcfile.createIfcRelDefinesByProperties(create_guid(), self.owner_history, None, None, [ifc_element],
                                                     element_quantity)


        # Relate the ifc_element to the building storey
        self.ifcfile.createIfcRelContainedInSpatialStructure(create_guid(), self.owner_history,
                                                             "Building Storey Container", None, [ifc_element],
                                                             self.building_storey)




"""

Point, Multipoint,  Line, Multiline, 
 Polygon ring, Polygon, Multipolygon, Geometry collection
 Compound* *Curve, 'COMPOUNDCURVE'...

"""

class Ogr2Shape:
    def __init__(self, ogr2ifc, feature):
        self.ogr2ifc = ogr2ifc
        self.feature = feature

    def geom_type(self, *types):
        return self.feature.GetGeometryRef().GetGeometryName().upper() in list([type.upper() for type in types])

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

        return float(top_elevation), float(bottom_elevation)

    def cog(self):
        raise NotImplementedError

    def box(self):
        raise NotImplementedError

    def axis(self):
        raise NotImplementedError

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
        extrusion_placement = create_ifcaxis2placement(self.ogr2ifc.ifcfile, (0.0, 0.0, bottom_elevation), Z, X)
        solids = self.create_ifcextrudedareasolids(extrusion_placement, Z, extrusion_distance)

        return [self.ogr2ifc.ifcfile.createIfcShapeRepresentation(self.ogr2ifc.context, "Body", "SweptSolid", solids)]

    ####################################################################################
    # Geometry
    # https://standards.buildingsmart.org/IFC/DEV/IFC4_3/RC1/HTML/schema/ifcrepresentationresource/lexical/ifcshaperepresentation.htm

    # Point
    def create_ifcpoints(self, points, dimensions=2):
        return [self.create_ifcpoint(point, dimensions) for point in points]

    def create_ifcpoint(self, point, dimensions=2):
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

    parser = argparse.ArgumentParser(description='Convert an ogc supported vector format file to an IFC file')
    parser.add_argument('dst_ifc_file', help='destination IFC file to be created')

    parser.add_argument('-top', help='Upper elevation for extruded IFC shape representations. '
                                                 'If text, GIS attribute value will be used')
    parser.add_argument('-bottom', help='Lower elevation for extruded IFC shape representations. '
                                                    'If text, GIS attribute value will be used')

    parser.add_argument('src_gis_file', help='source GIS vector file to be converted')
    parser.add_argument('layer', metavar='layername', nargs='?', help='layers to be converted, '
                                                                      'default: all layers will be converted')

    # Get user arguments
    args = parser.parse_args()

    # Recast top/bottom elevations to floats if possible
    try:
        args.top = float(args.top)
    except:
        pass
    try:
        args.bottom = float(args.bottom)
    except:
        pass

    o2i = Ogr2Ifc(gis_file_path=args.src_gis_file, bim_file_path=args.dst_ifc_file,
                  top_elevation=args.top, bottom_elevation=args.bottom)