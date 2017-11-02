# 4d-plugin-get-folder-size
Get total size of files inside folder

### Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|

### Version

<img src="https://cloud.githubusercontent.com/assets/1725068/18940649/21945000-8645-11e6-86ed-4a0f800e5a73.png" width="32" height="32" /> <img src="https://cloud.githubusercontent.com/assets/1725068/18940648/2192ddba-8645-11e6-864d-6d5692d55717.png" width="32" height="32" />

## Syntax

```
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

The plugins uses ``<filesystem>`` (MSVC, not ``boost``).

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

```
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

```
C_REAL($1)  //size
C_BOOLEAN($0)  //true to abort

Progress SET TITLE (PROGRESS;String($1))

$0:=<>STOP
```

* ``CB_STOP``

```
<>STOP:=True
```
