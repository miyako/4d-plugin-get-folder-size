/* --------------------------------------------------------------------------------
 #
 #  4DPlugin-Get-Folder-Size.cpp
 #	source generated by 4D Plugin Wizard
 #	Project : Get Folder Size
 #	author : miyako
 #	2025/03/22
 #  
 # --------------------------------------------------------------------------------*/

#include "4DPlugin-Get-Folder-Size.h"

#pragma mark -

void PluginMain(PA_long32 selector, PA_PluginParameters params) {
    
	try
	{
        switch(selector)
        {
			// --- Get Folder Size
            
			case 1 :
				Get_folder_size(params);
				break;

        }

	}
	catch(...)
	{

	}
}

#pragma mark -

#if VERSIONMAC

void Get_folder_size(PA_PluginParameters _params) {

    PackagePtr pParams = (PackagePtr)_params->fParameters;
    sLONG_PTR *pResult = (sLONG_PTR *)_params->fResult;
    
    C_TEXT Param1_path;
    C_TEXT Param2_method;
    C_REAL returnValue;

    Param1_path.fromParamAtIndex(pParams, 1);
    Param2_method.fromParamAtIndex(pParams, 2);
    
    PA_long32 methodId = PA_GetMethodID((PA_Unichar *)Param2_method.getUTF16StringPtr());
    BOOL useMethod = Param2_method.getUTF16Length() ? YES : NO;

    NSURL *url = Param1_path.copyUrl();
    NSFileManager *fileManager = [[NSFileManager alloc]init];
    
    NSDirectoryEnumerator *folderEnumerator = [fileManager enumeratorAtURL:url
                                                                                includingPropertiesForKeys:@[NSURLTotalFileSizeKey]
                                                                                                                     options:0
                                                                                                            errorHandler:nil];
    NSURL *item = nil;
    double total = 0;
    UInt64 count = 0;
    
    //prepare callback params
    PA_Variable    params[3];
    if(useMethod)
    {
        if(methodId)
        {
            params[0] = PA_CreateVariable(eVK_Real);
        }else
        {
            params[0] = PA_CreateVariable(eVK_Unistring);
            PA_Unistring methodName = PA_CreateUnistring((PA_Unichar *)Param2_method.getUTF16StringPtr());
            PA_SetStringVariable(&params[0], &methodName);
            params[1] = PA_CreateVariable(eVK_Boolean);
            PA_SetBooleanVariable(&params[1], false);
            params[2] = PA_CreateVariable(eVK_Real);
        }
    }
    
    BOOL aborted = NO;

    while ((item = [folderEnumerator nextObject]) && (!aborted))
    {
        NSNumber *totalFileSize = nil;
        if([item getResourceValue:&totalFileSize forKey:NSURLTotalFileSizeKey error:nil])
        {
            total += [totalFileSize doubleValue];
        }
        
        if(PA_IsProcessDying())
        {
            total = 0;
            aborted = YES;
        }else
        {
            //breathe every 8192 items
            if(((++count) % 0x2000)==0)
            {
                PA_YieldAbsolute();
                
                if(useMethod)
                {
                    if(methodId)
                    {
                        PA_SetRealVariable(&params[0], total);
                        PA_Variable ret = PA_ExecuteMethodByID(methodId, params, 1);
                        if(PA_GetVariableKind(ret) == eVK_Boolean)
                        {
                            if(PA_GetBooleanVariable(ret))
                            {
                                total = 0;
                                aborted = YES;
                            }
                        }
                    }else
                    {
                        //could be shared method
                        PA_SetRealVariable(&params[2], total);
                        PA_ExecuteCommandByID(1007, params, 3);
                        if(PA_GetBooleanVariable(params[1]))
                        {
                            total = 0;
                            aborted = YES;
                        }
                    }
                }
            }
        }
    }
    
    //clear callback params
    if(useMethod)
    {
        if(methodId)
        {
            PA_ClearVariable(&params[0]);
        }else
        {
            PA_ClearVariable(&params[0]);
            PA_ClearVariable(&params[1]);
            PA_ClearVariable(&params[2]);
        }
    }
    
    [fileManager release];
    [url release];

    returnValue.setDoubleValue(total);
    returnValue.setReturn(pResult);
}

#else

#include <iostream>
//#include <string>
#include <filesystem>

static double getFolderSize(std::wstring& rootFolder,
                                     double total,
                                     PA_ulong64 *count,
                                     BOOL useMethod,
                                     PA_long32 methodId,
                                     PA_Variable* params)
{
    std::filesystem::path folderPath(rootFolder);
    
    if (std::filesystem::exists(folderPath))
    {
        std::filesystem::directory_iterator end_itr;
        
        for (std::filesystem::directory_iterator dirIte(rootFolder); dirIte != end_itr; ++dirIte)
        {
            if(PA_IsProcessDying())
            {
                total = 0;
                break;
            }
            
            //breathe every 8192 items
            if(((++(*count)) % 0x2000)==0)
            {
                PA_YieldAbsolute();
                if(useMethod)
                {
                    if(methodId)
                    {
                        PA_SetRealVariable(&params[0], total);
                        PA_Variable ret = PA_ExecuteMethodByID(methodId, params, 1);
                        if(PA_GetVariableKind(ret) == eVK_Boolean)
                        {
                            if(PA_GetBooleanVariable(ret))
                            {
                                total = 0;
                                break;
                            }
                        }
                    }else
                    {
                        //could be shared method
                        PA_SetRealVariable(&params[2], total);
                        PA_ExecuteCommandByID(1007, params, 3);
                        if(PA_GetBooleanVariable(params[1]))
                        {
                            total = 0;
                            break;
                        }
                    }
                }
            
            }

            std::filesystem::path filePath(std::filesystem::weakly_canonical(folderPath / dirIte->path()));
            
            try
            {
                if (!std::filesystem::is_directory(dirIte->status()))
                {
                    total += std::filesystem::file_size(filePath);
                }else
                {
                    total = getFolderSize(filePath.wstring(), total, count, useMethod, methodId, params);
                }
            }catch(...)
            {
                
            }
        }
    }
    
    return total;
}

void Get_folder_size(PA_PluginParameters _params) {

    PackagePtr pParams = (PackagePtr)_params->fParameters;
    sLONG_PTR *pResult = (sLONG_PTR *)_params->fResult;
    
    C_TEXT Param1_path;
    C_TEXT Param2_method;
    C_REAL returnValue;
    
    Param1_path.fromParamAtIndex(pParams, 1);
    Param2_method.fromParamAtIndex(pParams, 2);
    
    PA_long32 methodId = PA_GetMethodID((PA_Unichar *)Param2_method.getUTF16StringPtr());
    BOOL useMethod = Param2_method.getUTF16Length() ? TRUE : FALSE;
    
    std::wstring rootFolderPath = std::wstring((wchar_t *)Param1_path.getUTF16StringPtr());
    if(rootFolderPath.length())
    {
        //remove trailing folder separator
        if(rootFolderPath.substr(rootFolderPath.length() - 1) == L"\\")
        {
            rootFolderPath = rootFolderPath.substr(0, rootFolderPath.length() - 1);
        }
    }

    double total = 0;
    PA_ulong64 count = 0;

    //prepare callback params
    PA_Variable    params[3];
    if(useMethod)
    {
        if(methodId)
        {
            params[0] = PA_CreateVariable(eVK_Real);
        }else
        {
            params[0] = PA_CreateVariable(eVK_Unistring);
            PA_Unistring methodName = PA_CreateUnistring((PA_Unichar *)Param2_method.getUTF16StringPtr());
            PA_SetStringVariable(&params[0], &methodName);
            params[1] = PA_CreateVariable(eVK_Boolean);
            PA_SetBooleanVariable(&params[1], false);
            params[2] = PA_CreateVariable(eVK_Real);
        }
    }
    
    PA_YieldAbsolute();

    total = getFolderSize(rootFolderPath, total, &count, useMethod, methodId, params);
    
    //clear callback params
    if(useMethod)
    {
        if(methodId)
        {
            PA_ClearVariable(&params[0]);
        }else
        {
            PA_ClearVariable(&params[0]);
            PA_ClearVariable(&params[1]);
            PA_ClearVariable(&params[2]);
        }
    }
    
    returnValue.setDoubleValue(total);
    returnValue.setReturn(pResult);
}

#endif
