from ogr2ifc.ogr2ifc import Ogr2Ifc

filename = "Gebaede.ifc"
file_path = './ifc_files/%s' % filename

if False:
    Ogr2Ifc('gis_files/complex.gpkg', file_path, bottom_elevation=350, top_elevation=380)
else:
    Ogr2Ifc('gis_files/complex.gpkg', file_path, bottom_elevation='bottom', top_elevation='top')



