from ogr2ifc.ogr2ifc import Ogr2Ifc

filename = "Gebaede.ifc"
file_path = './ifc_files/%s' % filename

Ogr2Ifc('gis_files/Gebaeude.shp', file_path,
        bottom_elevation=350, top_elevation=380)



