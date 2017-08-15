CONTAINER ColladaExportSettings
{
	NAME ColladaExportSettings;
    INCLUDE Texpression;
    
    GROUP ID_TAGPROPERTIES
	{
		BOOL COLLADA_EXPORT_SETTINGS_ENABLE_EXPORT { ANIM OFF; }

		GROUP 
		{
			FIT_H;
			COLUMNS 4;

			BOOL COLLADA_EXPORT_SETTINGS_EXTERNAL_TEXTURE { ANIM OFF; }
			LONG COLLADA_EXPORT_SETTINGS_TEXTURETYPE 
			{
				ANIM OFF;
				FIT_H; SCALE_H;
				CYCLE
				{
					COLLADA_EXPORT_SETTINGS_TEXTURETYPE_SVG;
					COLLADA_EXPORT_SETTINGS_TEXTURETYPE_BITMAP;
				}
			}
		}
	}
}