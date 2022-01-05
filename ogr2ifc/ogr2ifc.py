
import os
import uuid
import time
import ogr
import shapely
#from shapely import wkt
import ifcopenshell
from ifcopenshell.template import TEMPLATE, create, DEFAULTS

# ToDO: Curve geometry
# ToDO: Space instead of building
# ToDO: Attributes
# ToDo: Make OO provide ability to do individual layers and objects
# ToDo: Command line version with arguments

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
# Geometry

def create_ifcpoint(ifcfile, point, dimensions=2):
    return ifcfile.createIfcCartesianPoint(point[:dimensions])

# Creates an IfcPolyLine from a list of points, specified as Python tuples
def create_ifcpolyline(ifcfile, point_list):
    ifcpts = [create_ifcpoint(ifcfile, point) for point in point_list]
    polyline = ifcfile.createIfcPolyLine(ifcpts)
    return polyline


# Supports multigeometry. Returns list of extruded solids (if single geometry, list of length one)
def create_ifcextrudedareasolids(ifcfile, feature, ifcaxis2placement, extrude_dir, extrusion):
    geomref = feature.GetGeometryRef()  # Object
    return [create_ifcextrudedareasolid(ifcfile, geomref.GetGeometryRef(i), ifcaxis2placement, extrude_dir, extrusion)
            for i in range(geomref.GetGeometryCount())]


# Creates an createIfcArbitraryClosedProfileDef or IfcArbitraryProfileDefWithVoids from an ogc feature
def create_ifcextrudedareasolid(ifcfile, geomref, ifcaxis2placement, extrude_dir, extrusion):
    geomcount = geomref.GetGeometryCount()

    # Outer ring
    outer_ring = geomref.GetGeometryRef(0)
    point_list = [outer_ring.GetPoint(i) for i in range(outer_ring.GetPointCount())]
    outer_polyline = create_ifcpolyline(ifcfile, point_list)

    # Create profile
    if geomcount == 1:  # Simple profile
        ifc_profile = ifcfile.createIfcArbitraryClosedProfileDef("AREA", None, outer_polyline)
    else:  # Has inner voids/holes
        # Inner bounds
        inner_polylines = []
        for j in range(1, geomcount):
            inner_ring = geomref.GetGeometryRef(j)
            point_list = [inner_ring.GetPoint(i) for i in range(inner_ring.GetPointCount())]
            inner_polylines.append(create_ifcpolyline(ifcfile, point_list))

        # IfcArbitraryProfileDefWithVoids
        ifc_profile = ifcfile.createIfcArbitraryProfileDefWithVoids("AREA", None, outer_polyline, inner_polylines)

    # Extrude profile to solid
    ifcdir = ifcfile.createIfcDirection(extrude_dir)
    ifcextrudedareasolid = ifcfile.createIfcExtrudedAreaSolid(ifc_profile, ifcaxis2placement, ifcdir, extrusion)
    return ifcextrudedareasolid


####################################################################################
# Class

class Ogr2Ifc:
    def __init__(self, gis_file_path, bim_file_path, top_elevation=10000, bottom_elevation=0):
        """

        :param gis_file_path: Path to ogr supported vector GIS file
        :param bim_file_path: Path to save IFC file
        :param top_elevation: Upper elevation of extruded volume. If text, GIS attribute value will be used,
        or self.max_elevation if NULL or not available
        :param bottom_elevation: Lower elevation of extruded volume. If text, GIS attribute value will be used,
        or self.min_elevation if NULL or not available
        """

        self.max_elevation = 10000  # default maximum extruded elevation
        self.min_elevation = 0  # default minimum extruded elevation
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
        self.dataSource = ogr.Open(gis_file_path)
        self.add_vector_layers()

        # Save ifc file
        self.ifcfile.write(bim_file_path)
        print(f'File written to {bim_file_path}')

    def __del__(self):
        self.dataSource.Destroy()

    def add_vector_layers(self):
        for layer in self.dataSource:
            # Add features
            self.add_layer_objects(layer)

    def add_layer_property_set(self, layer, feature, ifc_element):
        layername = layer.GetName()

        """
        layerDefinition = layer.GetLayerDefn()

        for i in range(layerDefinition.GetFieldCount()):
            field = layerDefinition.GetFieldDefn(i)  # Name and Type
            fieldName = field.GetName()
            fieldTypeCode = field.GetType()
            fieldType = field.GetFieldTypeName(fieldTypeCode)
            fieldWidth = field.GetWidth()
            field_precision = field.GetPrecision()
        """

        # Create and assign property set
        attributes = feature.items()
        property_values = list()

        for k, v in attributes.items():  # toDo: Dates etc...
            if isinstance(v, bool):
                property_values.append(
                    self.ifcfile.createIfcPropertySingleValue(k, k, self.ifcfile.create_entity("IfcBoolean", v), None))
            elif isinstance(v, int):
                property_values.append(
                    self.ifcfile.createIfcPropertySingleValue(k, k, self.ifcfile.create_entity("IntValue", v), None))
            elif isinstance(v, float):
                property_values.append(
                    self.ifcfile.createIfcPropertySingleValue(k, k, self.ifcfile.create_entity("IfcReal", v), None))
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

        product_shape = self.ifcfile.createIfcProductDefinitionShape(None, None, [self.body_representation(feature)])

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

    def body_representation(self, feature):

        geomref = feature.GetGeometryRef()  # Object
        geomname = geomref.GetGeometryName().upper()  # 'MULTIPOLYGON', 'COMPOUNDCURVE'...

        if geomname in ('POLYGON', 'MULTIPOLYGON'):
            return self.swept_solid(feature)
        else:
            """ Point, Multipoint,  Line, Multiline,  *Curve,  Geometry collection """
            raise Exception('Geom type %s not supported yet' % geomname)

    def swept_solid(self, feature):
        # Obtain extrusion information if attribute information
        if isinstance(self.bottom_elevation, str):
            bottom_elevation = feature.items().get(self.bottom_elevation)
            if bottom_elevation is None:
                print('Bottom elevation for feature %s set to min' % feature.GetFID())
                bottom_elevation = self.min_elevation
        else:
            bottom_elevation = self.bottom_elevation

        if isinstance(self.top_elevation, str):
            top_elevation = feature.items().get(self.top_elevation)
            if top_elevation is None:
                print('Top elevation for feature %s set to max' % feature.GetFID())
                top_elevation = self.max_elevation
        else:
            top_elevation = self.top_elevation

        extrusion_distance = top_elevation - bottom_elevation

        extrusion_placement = create_ifcaxis2placement(self.ifcfile, (0.0, 0.0, float(bottom_elevation)), Z, X)

        solids = create_ifcextrudedareasolids(self.ifcfile, feature, extrusion_placement, Z, extrusion_distance)
        return self.ifcfile.createIfcShapeRepresentation(self.context, "Body", "SweptSolid", solids)

