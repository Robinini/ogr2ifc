
import ifcopenshell
from ifcopenshell.template import TEMPLATE, create, DEFAULTS
from ogr2ifc.ogr2ifc import create_guid as create_guid, create_ifclocalplacement, create_ifcpolyline, \
    create_ifcaxis2placement, create_ifcextrudedareasolid



ifc_file = ifcopenshell.open("ifc_files/William.ifc")
products = ifc_file.by_type("IfcProduct")
print(products[0].id(), products[0].GlobalId)