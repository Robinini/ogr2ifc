from ogr2ifc import Ogr2Ifc, transformer

gis_file = './gis_files/points.sqlite'
ifc_file = './ifc_files/test.ifc'

# Create coordinate transformation function
coord_tran = transformer(eastings=2719310, northings=1225070,
                         orthogonal_height=410.10, rotation=44.2939)

bottom_elevation = 370
top_elevation = 430

# Convert
o2i = Ogr2Ifc(gis_file_path=gis_file,
              bottom_elevation=bottom_elevation, top_elevation=top_elevation,
              coord_transformer=coord_tran
              )
o2i.add_vector_layers()
o2i.save_ifc(ifc_file)





