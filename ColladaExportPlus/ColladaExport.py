import os, uuid, ntpath
import xml.etree.ElementTree as ET
import c4d
from c4d import plugins, documents, storage, gui
from math import floor

# Constants
uuidString = str( uuid.uuid1() )
colladaPluginId = 1025755
colladaExportTagId = 1039717
textureTagId = 5616
noExportFlag = 'NO_EXPORT'
nullTypeName = 'Null'
xrefTypeName = 'XRef'
xrefInteriorObjTag = '::'

metadataTagID = 'META'
metadataTagAlpha = 'AL'
metadataTagColor = 'CO'
metadataTagCount = 'ID'

# Add a uuid to end of the polygon object name. 
# This prevents the names from colliding with existing
# objects in the scene when they are deleted
polygonName = 'Polygon' + uuidString

# Setup COLLADA XML namespace
colladaSchemaURI = 'http://www.collada.org/2008/03/COLLADASchema'
ns = '{' + colladaSchemaURI + '}'
nsPrefix = 'COLLADA_NAMESPACE' + uuidString
ET._namespace_map[ colladaSchemaURI ] = nsPrefix

class ColladaExport():

    # COLLADA Export tag ids 
    COLLADA_EXPORT_SETTINGS_ENABLE_EXPORT = 1017
    COLLADA_EXPORT_SETTINGS_EXTERNAL_TEXTURE = 1018
    COLLADA_EXPORT_SETTINGS_TRANSFER_COLOR = 1019
    COLLADA_EXPORT_SETTINGS_USE_TEXTURE_ALPHA = 1020
    COLLADA_EXPORT_SETTINGS_CUSTOM_DATA = 1021
    COLLADA_EXPORT_SETTINGS_MERGE_CHILDREN = 1022

    doc = None
    docCopy = None
    xrefCounter = 0
    polyCounter = 0

    def __init__( self, name = 'ColladaExport' ):
        self.name = name
        self.idCounter = 0;


    def Execute( self, filepath, exportanim, exportnulls, removexrefs, removetextags ):
        self.doc = documents.GetActiveDocument()
        assert self.doc is not None

        c4d.StopAllThreads()

        # Get the COLLADA export plugin
        colladaPlugin = plugins.FindPlugin( colladaPluginId, c4d.PLUGINTYPE_SCENESAVER )
        assert colladaPlugin is not None

        # Perform requested geometry merges, can only be done on current document,
        # so this will be undone at the end.
        mergeObjects = self.GetMergeGeometryObjs( self.doc.GetFirstObject(), [] )
        self.MergeGeometry( mergeObjects )

        # Clone the current document so the modifications aren't applied to the original scene
        self.docCopy = self.doc.GetClone( c4d.COPYFLAGS_DOCUMENT )
        assert self.docCopy is not None

        # Remove xrefs
        if removexrefs is True:
            self.RemoveXRefs( self.docCopy.GetFirstObject() )

        # Remove objects that are on non-exporting layers
        removeObjects = self.RemoveNonExporting( self.docCopy.GetFirstObject(), [] )
        for op in removeObjects: 
            op.Remove()

        # Add object export settings as metadata appended to object names
        self.ExportDataToNameMeta( self.docCopy.GetFirstObject() )

        # Add object GUIDs to object names, to force a unique name
        self.ExportGUIDToName( self.docCopy.GetFirstObject() )

        # Collect warnings for names that are too long
        self.WarnIfLongName( self.docCopy.GetFirstObject() )

        # Add empty polygon objects to childless null objects so that they are exported by the
        # COLLADA exporter
        if exportnulls is True:
            self.FixUpEmptyNulls( self.docCopy.GetFirstObject() )

        # Remove teture tags
        if removetextags is True:
            self.RemoveTextureTags( self.docCopy.GetFirstObject() )

        # Container for plugin object data
        op = {}

        # Configure COLLADA export plugin and export the modified scene
        assert colladaPlugin.Message( c4d.MSG_RETRIEVEPRIVATEDATA, op )
        assert 'imexporter' in op

        # Get the exporter settings from the plugin object
        colladaExport = op[ 'imexporter' ]
        assert colladaExport is not None

        # Define the settings
        colladaExport[ c4d.COLLADA_EXPORT_ANIMATION ] = exportanim
        colladaExport[ c4d.COLLADA_EXPORT_TRIANGLES ] = True
        
        # Export without the dialog
        if c4d.documents.SaveDocument( self.docCopy, filepath, c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST, colladaPluginId ):
            
            # Parse the saved COLLADA data as XML
            colladaData = ET.parse( filepath )
            parentMap = dict( ( c, p ) for p in colladaData.getiterator() for c in p )
            
            # Construct geometry id map
            geomIdMap = dict()
            for node in colladaData.getiterator():
                if node.tag == ns + 'geometry':
                    geomIdMap[ node.get( 'id' ) ] = node

            # Get first effect and material nodes to prevent them from being deleted
            firstEffectNode = colladaData.find( './/' + ns + 'effect' )
            firstMaterialNode = colladaData.find( './/' + ns + 'material' )
            firstMaterialId = firstMaterialNode.get( 'id' )
            
            # Iterate thru the hierarchy and deal with things
            for node in colladaData.getiterator():

                # Remove Polygon objects and associated geometry data
                if node.tag == ns + 'node':
                    if node.get( 'name' ) == polygonName:
                        geomId = node.find( ns + 'instance_geometry' ).get( 'url' )[ 1: ]
                        geomNode = geomIdMap[ geomId ]
                        parentMap[ geomNode ].remove( geomNode )
                        parentMap[ node ].remove( node )

                # Remove library_images tags
                if node.tag == ns + 'library_images':
                    parentMap[ node ].remove( node )

                # Remove effect tags except for the first one
                if node.tag == ns + 'effect':
                    if node != firstEffectNode:
                        parentMap[ node ].remove( node )

                # Remove material tags except for the first one
                if node.tag == ns + 'material':
                    if node != firstMaterialNode:
                        parentMap[ node ].remove( node )

                # Set material target to the first material id
                if node.tag == ns + 'instance_material':
                    node.set( 'target', '#' + firstMaterialId )
            
            # Remove the namespace from all tags
            xmlString = ET.tostring( colladaData.getroot() )
            xmlString = xmlString.replace( nsPrefix + ':', '' )
            xmlString = xmlString.replace( ':' + nsPrefix, '' )

            # Write the modified COLLADA file
            colladaFile = open( filepath, 'w' )
            colladaFile.write( xmlString )
            colladaFile.close()

            # Cleanup
            if len( mergeObjects ) is not 0:

                for op in mergeObjects:
                    for x in range( 0, 3 ):
                        self.doc.DoUndo( False )

                self.doc.DoUndo( False )
                self.doc.DoUndo( False )

            return 'Export complete\n\nRemoved %d xrefs\nFixed %d empty null objects' % ( self.xrefCounter, self.polyCounter )
        else:
            return 'The document failed to save.'


    def RemoveXRefs( self, op ):

        while op:

            # Names with "::" in them are internal objects derived from xrefs. 
            # Since the xrefs will be replaced when importing into js,
            # their internals don't need to be exported here.
            if xrefInteriorObjTag in op.GetName():
                break

            if xrefTypeName in op.GetTypeName():
                self.xrefCounter += 1
                op.Remove()
                break

            # Recurse thru the hierarchy
            self.RemoveXRefs( op.GetDown() )
            op = op.GetNext()

    def RemoveNonExporting( self, op, list ):

        while op:

            remove = False

            # Remove if render display mode is off
            if op.GetRenderMode() is c4d.MODE_OFF:
                remove = True

            # Remove if editor display mode is off 
            if op.GetEditorMode() is c4d.MODE_OFF:
                remove = True

            # Remove if the object has the COLLADA export tag and is set to not export
            exportTag = op.GetTag( colladaExportTagId )
            if exportTag is not None:
                if exportTag.GetData().GetBool( self.COLLADA_EXPORT_SETTINGS_ENABLE_EXPORT ) is False:
                    remove = True

            if remove is True:
                list.append( op )

            # Recurse thru the hierarchy
            self.RemoveNonExporting( op.GetDown(), list )
            op = op.GetNext()

        return list


    def RemoveTextureTags( self, op ):

        while op:

            op.KillTag( textureTagId )

            # Recurse thru the hierarchy
            self.RemoveTextureTags( op.GetDown() )
            op = op.GetNext()


    def FixUpEmptyNulls( self, op ):

        while op:

            # Add empty polygon objects to any null nodes with no children, so 
            # that they are exported by the COLLADA exporter correctly.
            if nullTypeName in op.GetTypeName():
                if len( op.GetChildren() ) == 0:
                    polyOp = c4d.PolygonObject( 0, 0 )
                    polyOp.SetName( polygonName )
                    polyOp.InsertUnder( op )
                    self.polyCounter += 1

            # Recurse thru the hierarchy
            self.FixUpEmptyNulls( op.GetDown() )
            op = op.GetNext()


    def GetMergeGeometryObjs( self, op, objects ):

        while op:

            # Names with "::" in them are internal objects derived from xrefs. 
            # Since the xrefs will be replaced when importing into js,
            # their internals don't need to be exported here.
            if xrefInteriorObjTag in op.GetName():
                break

            exportTag = op.GetTag( colladaExportTagId )

            if exportTag is not None:

                data = exportTag.GetData()
                shouldMerge = data.GetBool( self.COLLADA_EXPORT_SETTINGS_MERGE_CHILDREN )

                if shouldMerge is True:

                    objects.append( op )

            self.GetMergeGeometryObjs( op.GetDown(), objects )
            op = op.GetNext()

        return objects


    def MergeGeometry( self, objects ):

        for op in objects: 

            # Set selection to root node
            self.doc.SetSelection( op )

            # Select children
            c4d.CallCommand( 100004768 )

            # Make editable
            c4d.CallCommand( 12236 )

            # Set selection to root node
            self.doc.SetSelection( op )

            # Select children
            c4d.CallCommand( 100004768 )

            # Connect objects and delete
            c4d.CallCommand( 16768 )


    def ExportGUIDToName( self, op ):

        while op:

            op.SetName( op.GetName() + '___' + metadataTagCount + '_' + str( self.idCounter ) )

            self.idCounter = self.idCounter + 1

            # Recurse thru the hierarchy
            self.ExportGUIDToName( op.GetDown() )
            op = op.GetNext()


    def WarnIfLongName( self, op ):

        while op:

            if len( op.GetName() ) > 63:
                print 'WARNING: Name \"' + op.GetName() + '\" is too long!' 

            self.WarnIfLongName( op.GetDown() )
            op = op.GetNext()


    def ExportDataToNameMeta( self, op ):

        while op:

            exportTag = op.GetTag( colladaExportTagId )

            if exportTag is not None:

                # Extract data from the export tag
                data = exportTag.GetData()
                texPath = data.GetFilename( self.COLLADA_EXPORT_SETTINGS_EXTERNAL_TEXTURE )
                useAlpha = data.GetBool( self.COLLADA_EXPORT_SETTINGS_USE_TEXTURE_ALPHA )
                transferColor = data.GetBool( self.COLLADA_EXPORT_SETTINGS_TRANSFER_COLOR )
                customData = data.GetString( self.COLLADA_EXPORT_SETTINGS_CUSTOM_DATA )

                useNameMetadata = False

                texNameMetadata = metadataTagID
                texNameMetadata += '___'

                # Add texture filename metadata
                if len( texPath ) is not 0:

                    fileName = ntpath.basename( texPath )
                    fileExt = ntpath.splitext( texPath )[ 1 ].upper()

                    # Append the texture file name to the end of the object's name
                    # It gets a special label if it's an SVG, since those are handled
                    # differently than normal textures
                    texNameMetadata += 'SVG' if fileExt == '.SVG' else 'TEX'
                    texNameMetadata += '_' + fileName

                    if useAlpha is True:
                        texNameMetadata += '___' + metadataTagAlpha

                    useNameMetadata = True

                # Add material color metadata
                if transferColor is True:

                    texTag = op.GetTag( textureTagId )

                    if texTag is not None: 

                        material = texTag.GetMaterial()

                        if material is not None:

                            # Get luminance channel color and convert it to a hex string value
                            color = material.GetAverageColor( c4d.CHANNEL_LUMINANCE )
                            r = floor( min( color.x, 1 ) * 255 )
                            g = floor( min( color.y, 1 ) * 255 )
                            b = floor( min( color.z, 1 ) * 255 )
                            hex = '%02x%02x%02x' % ( r, g, b )

                            # Add field separator if required
                            if texPath is not None: 
                                texNameMetadata += '___'
                        
                            texNameMetadata += metadataTagColor + '_' + hex

                            useNameMetadata = True

                # Add additional custom metadata
                if len( customData ) is not 0:

                    for dataItem in customData.split( ',' ): 
                        texNameMetadata += '__'

                        for dataPiece in dataItem.split():
                            texNameMetadata += '_' + dataPiece
                            useNameMetadata = True

                # Append metadata to the object's name
                if useNameMetadata is True:
                    op.SetName( op.GetName() + texNameMetadata )

            # Recurse thru the hierarchy
            self.ExportDataToNameMeta( op.GetDown() )
            op = op.GetNext()
