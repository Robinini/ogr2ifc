
import os
import uuid
import time
import ogr
import shapely
import ifcopenshell
from ifcopenshell.template import TEMPLATE, create, DEFAULTS



####################################################################################
# IFC

O = 0., 0., 0.
X = 1., 0., 0.
Y = 0., 1., 0.
Z = 0., 0., 1.

#Helper functions
# Creates an IfcAxis2Placement3D from Location, Axis and RefDirection specified as Python tuples
def create_ifcaxis2placement(ifcfile, point=O, dir1=Z, dir2=X):
    point = ifcfile.createIfcCartesianPoint(point)
    dir1 = ifcfile.createIfcDirection(dir1)
    dir2 = ifcfile.createIfcDirection(dir2)
    axis2placement = ifcfile.createIfcAxis2Placement3D(point, dir1, dir2)
    return axis2placement


# Creates an IfcLocalPlacement from Location, Axis and RefDirection, specified as Python tuples, and relative placement
def create_ifclocalplacement(ifcfile, point=O, dir1=Z, dir2=X, relative_to=None):
    axis2placement = create_ifcaxis2placement(ifcfile,point,dir1,dir2)
    ifclocalplacement2 = ifcfile.createIfcLocalPlacement(relative_to,axis2placement)
    return ifclocalplacement2


# Creates an IfcPolyLine from a list of points, specified as Python tuples
def create_ifcpolyline(ifcfile, point_list):
    ifcpts = []
    for point in point_list:
        point = ifcfile.createIfcCartesianPoint(point)
        ifcpts.append(point)
    polyline = ifcfile.createIfcPolyLine(ifcpts)
    return polyline


# Creates an IfcExtrudedAreaSolid from a list of points, specified as Python tuples
def create_ifcextrudedareasolid(ifcfile, point_list, ifcaxis2placement, extrude_dir, extrusion):
    polyline = create_ifcpolyline(ifcfile, point_list)
    ifcclosedprofile = ifcfile.createIfcArbitraryClosedProfileDef("AREA", None, polyline)
    ifcdir = ifcfile.createIfcDirection(extrude_dir)
    ifcextrudedareasolid = ifcfile.createIfcExtrudedAreaSolid(ifcclosedprofile, ifcaxis2placement, ifcdir, extrusion)
    return ifcextrudedareasolid


create_guid = lambda: ifcopenshell.guid.compress(uuid.uuid1().hex)


class Ogr2Ifc:
    def __init__(self, gis_file_path, bim_file_path,
                 bottom_elevation=0, top_elevation=10000):

        self.bottom_elevation = bottom_elevation
        self.top_elevation = top_elevation
        self.extrusion_distance = self.top_elevation - self.bottom_elevation

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
                                                                    None, None, "ELEMENT", bottom_elevation)

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

    def __del__(self):
        self.dataSource.Destroy()

    def add_vector_layers(self):
        for layer in self.dataSource:
            # Add layer propertysets
            self.add_layer_property_set(layer)

            # Add features
            self.add_layer_objects(layer)

    def add_layer_property_set(self, layer):
        # ToDo
        return
        layername = layer.GetName()
        layerDefinition = layer.GetLayerDefn()

        for i in range(layerDefinition.GetFieldCount()):
            field = layerDefinition.GetFieldDefn(i)  # Name and Type fieldName = field.GetName()
            fieldTypeCode = field.GetType()
            fieldType = field.GetFieldTypeName(fieldTypeCode)
            fieldWidth = field.GetWidth()
            field_precision = field.GetPrecision()

    def add_layer_objects(self, layer):
        layername = layer.GetName()

        for feature in layer:
            self.add_feature(layername, feature)

    def add_feature(self, layername, feature):

        ############################################
        # Wall creation: Define the ifc_element shape as a polyline axis and an extruded area solid
        feature_placement = create_ifclocalplacement(self.ifcfile, relative_to=self.storey_placement)

        product_shape = self.ifcfile.createIfcProductDefinitionShape(None, None, [self.body_representation(feature)])

        ifc_element = self.ifcfile.createIfcWallStandardCase(create_guid(), self.owner_history, "GIS Feature",
                                                             "An GIS2BIM ifc_element",
                                                             None, feature_placement, product_shape, None)

        # Create and assign property set
        property_values = list()
        property_values.append(self.ifcfile.createIfcPropertySingleValue("Reference", "Reference",
                                                                         self.ifcfile.create_entity("IfcText",
                                                                                                    "GIS feature"),
                                                                         None))
        property_values.append(self.ifcfile.createIfcPropertySingleValue("IsExternal", "IsExternal",
                                                                         self.ifcfile.create_entity("IfcBoolean", True),
                                                                         None))
        property_values.append(self.ifcfile.createIfcPropertySingleValue("ThermalTransmittance", "ThermalTransmittance",
                                                                         self.ifcfile.create_entity("IfcReal", 2.569),
                                                                         None))
        property_values.append(self.ifcfile.createIfcPropertySingleValue("IntValue", "IntValue",
                                                                         self.ifcfile.create_entity("IfcInteger", 2),
                                                                         None))

        property_set = self.ifcfile.createIfcPropertySet(create_guid(), self.owner_history,
                                                         "Pset_WallCommon", None, property_values)
        self.ifcfile.createIfcRelDefinesByProperties(create_guid(), self.owner_history, None, None, [ifc_element],
                                                     property_set)

        # Add quantity information
        """
        quantity_values = [self.ifcfile.createIfcQuantityArea("Area", "Area of the front face", None, self.area(feature))]
        element_quantity = self.ifcfile.createIfcElementQuantity(create_guid(), self.owner_history, "BaseQuantities",
                                                                 None, None, quantity_values)
        self.ifcfile.createIfcRelDefinesByProperties(create_guid(), self.owner_history, None, None, [ifc_element],
                                                     element_quantity)
        """

        # Relate the ifc_element to the building storey
        self.ifcfile.createIfcRelContainedInSpatialStructure(create_guid(), self.owner_history,
                                                             "Building Storey Container", None, [ifc_element],
                                                             self.building_storey)

    def body_representation(self, feature):
        #Todo Point > ?, Line > ?

        geomref = feature.GetGeometryRef()  # Object
        geomname = geomref.GetGeometryName()  # 'MULTIPOLYGON'...
        print(geomname)

        pointnr = geomref.GetPointCount()  # Number of points
        print(pointnr)

        for i in range(pointnr):
            points = geomref.GetPoint(i)  # (x,y,z)
            print(points)
            x = geomref.GetX(i)  # also GetY, GetZ. Number
        wktText = geomref.ExportToWkt()  # Other formats TI,C15,P81 teilgeomnr = geomref.GetGeomertyCount() # Nr Part Geo
        print(wktText)

        extrusion_placement = create_ifcaxis2placement(self.ifcfile, (0.0, 0.0, 0.0), Z, X)
        point_list_extrusion_area = [(0.0, -0.1, 0.0), (5.0, -0.1, 0.0), (5.0, 0.1, 0.0), (0.0, 0.1, 0.0),
                                     (0.0, -0.1, 0.0)]

        solid = create_ifcextrudedareasolid(self.ifcfile, point_list_extrusion_area, extrusion_placement, Z,
                                            self.extrusion_distance)
        return self.ifcfile.createIfcShapeRepresentation(self.context, "Body", "SweptSolid", [solid])

    def area(self, feature):
        return  #ToDO
        # "Convert" Geometry to shapely-geometry
        wkt_geometry = feature.GetGeometryRef().ExportToWkt()
        shapely_geometry = shapely.wkt.loads(wkt_geometry)
        return shapely_geometry.area
