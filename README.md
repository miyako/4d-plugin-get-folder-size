![version](https://img.shields.io/badge/version-20%2B-E23089)
![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm%20|%20win-64&color=blue)
[![license](https://img.shields.io/github/license/miyako/4d-plugin-get-folder-size)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/4d-plugin-get-folder-size/total)

# 4d-plugin-get-folder-size
Get total size of files inside folder

## Syntax

```4d
size:=Get folder size(path{;method})
```

Parameter|Type|Description
------------|------------|----
path|TEXT|
method|TEXT|
size|REAL|

### Signature for ``method``

Parameter|Type|Description
------------|------------|----
size|REAL|
stop|BOOL|``true`` to abort

## Discussion

* Windows

There are several ways to traverse a directory tree.

The plugins uses [``<filesystem>``](https://msdn.microsoft.com/en-us/library/hh874694.aspx) (MSVC, not ``boost``) [``file_size``](https://msdn.microsoft.com/en-us/library/hh874829.aspx).

This is basically the number of bytes you see in Explorer "Size" property, not "Size on disk".

* macOS

There are several ways to measure a file's size. 

[``NSURLTotalFileSizeKey``](https://developer.apple.com/documentation/foundation/nsurlresourcekey?language=objc) is used.

This is basically the number of bytes you see in Finder "Get Info".

[``NSDirectoryEnumerationOptions``](https://developer.apple.com/documentation/foundation/nsdirectoryenumerationoptions?language=objc) is not used. In otherwords, it descend into directories, it descend into packages and it enumerates hidden files.

The plugin yields to 4D every ``0x2000`` items. That's ``8192`` folders and files.

If passed, it also executes the callback method.

## Examples

* Without callback

```
$path:="Macintosh HD:Users:miyako:Downloads:sample:"
$size:=Get folder size ($path)
```

* With callback

```4d
$path:="Macintosh HD:Users:miyako:Downloads:sample:"

PROGRESS:=Progress New 
Progress SET PROGRESS (PROGRESS;-1)
Progress SET BUTTON ENABLED (PROGRESS;True)
Progress SET ON STOP METHOD (PROGRESS;"CB_STOP")

<>STOP:=False

$size:=Get folder size ($path;"CB")

Progress QUIT (PROGRESS)
```

* ``CB``

```4d
C_REAL($1)  //size
C_BOOLEAN($0)  //true to abort

Progress SET TITLE (PROGRESS;String($1))

$0:=<>STOP
```

* ``CB_STOP``

```4d
<>STOP:=True
```
