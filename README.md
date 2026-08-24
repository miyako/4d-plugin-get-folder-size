![version](https://img.shields.io/badge/version-20%2B-E23089)
![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm%20|%20win-64&color=blue)
[![license](https://img.shields.io/github/license/miyako/4d-plugin-get-folder-size)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/4d-plugin-get-folder-size/total)

# 4d-plugin-get-folder-size

The Get Folder Size plugin computes the total size, in bytes, of every file inside a folder and all its subfolders, driven by the OS's native file-enumeration APIs — `NSFileManager`/`NSDirectoryEnumerator` (reading the `NSURLTotalFileSizeKey` resource key) on macOS, and the C++17 `<filesystem>` API (`directory_iterator` + `file_size`) on Windows. It returns a single `Real` value. Optionally, it reports progress — and lets you abort the scan early — through a 4D method you supply.

## Summary

Command | Returns | Purpose
------------|------------|----
[Get folder size](#get-folder-size) | Real | Total size in bytes of all files under a folder, with an optional progress/abort callback.

**Platforms:** macOS (Intel & Apple Silicon) · Windows (64-bit)

---

## Requirements & platform notes

- **Two parameters, one mandatory.** `path` is required. `method` is optional — omit it entirely for a plain, non-interactive call (see the `Method1` example below).
- **No explicit minimum-OS check.** The plugin doesn't test or enforce a specific OS version at runtime. The version badge above indicates 4D 20 or later; beyond that, no concrete OS-version floor could be confirmed from the source, so none is asserted here.
- **"Size" means logical file size, not size-on-disk.** On Windows this is the number you'd see in Explorer's "Size" property; on macOS it's the number in Finder's "Get Info" panel. Neither matches the "Size on disk" figure Explorer/Finder also show, which rounds up to filesystem block boundaries.
- **Nothing is filtered out.** Hidden files, dotfiles, and the contents of package/bundle-style folders are all included in the total on both platforms — the plugin doesn't skip any category of item.
- **On Windows, symlinked/junctioned subfolders are followed**, with no cycle detection. If a folder tree contains a symbolic link or junction that loops back to one of its own ancestors, the scan currently has no protection against that — treat deeply symlinked trees as an untested edge case.
- **Thread-safe.** The plugin is declared thread-safe, so it's safe to call from a preemptive/worker process without blocking your main 4D process while a large folder is scanned.
- **Progress cadence:** the plugin checks for a user interrupt and invokes your callback (if any) once every 8192 files/folders processed — not on a timer, so callback frequency in wall-clock time depends on how fast the underlying disk/filesystem can enumerate entries.

---

## Get folder size

### Syntax

```
size:=Get folder size(path{;method})
```

Parameter | Type | Description
------------|------------|----
`path` | Text | Folder to measure. Bytes of every file in this folder and all its subfolders are summed.
`method` | Text | Optional. Name of a 4D method to call periodically while the folder is scanned, so you can display progress and, if you choose, abort the scan. Omit it to run with no callback.
Result | Real | Total size, in bytes, of all files under `path`. Returns `0` if `path` doesn't exist or is empty, and also returns `0` if the callback aborts the scan (see below) — not the partial size counted so far.

### Description

`Get folder size` walks `path` recursively, summing the byte size of every file it finds. On macOS this uses `NSDirectoryEnumerator` over `NSURLTotalFileSizeKey`; on Windows it walks `std::filesystem::directory_iterator` and reads `std::filesystem::file_size` per entry.

**Callback signature.** If you pass `method`, it's called periodically with exactly this signature (confirmed from the plugin's own `CB.4dm` test method):

```4d
C_REAL($1)      //running total, in bytes, counted so far
C_BOOLEAN($0)   //return true to abort the scan
```

**Aborting discards the total, it doesn't return it.** If your callback returns `true`, `Get folder size` stops scanning immediately and its result is `0` — the bytes counted up to that point are *not* returned. If you need the partial size after an abort, capture `$1` yourself inside the callback (for example into an interprocess variable) before returning `true`.

**A non-boolean callback result is silently ignored.** If your callback doesn't return a boolean at all, the abort check is simply skipped for that call and the scan continues uninterrupted — no 4D error is raised either way.

**Invalid or missing folders fail silently.** Passing a `path` that doesn't exist, or an empty string, doesn't raise a 4D error — the command just returns `0`.

### Example

From the plugin's own test method (`Method1.4dm`), without a callback:

```4d
$path:=System folder:C487(Desktop:K41:16)

$size:=Get folder size($path)
```

From the plugin's own test methods (`Method2.4dm`, `CB.4dm`, `CB_STOP.4dm`), with a progress callback tied to a progress bar:

> `Progress New`, `Progress SET PROGRESS`, `Progress SET BUTTON ENABLED`, `Progress SET ON STOP METHOD`, and `Progress QUIT` below are **not part of this plugin** — they come from a separate progress-bar component/toolkit the sample project happens to use. They're shown here only because they're what the plugin's own test files use to demonstrate the callback; the `Get folder size` call itself doesn't require them. Omit them (and drive your own UI instead) if you don't have that component installed.

`Method2.4dm`:
```4d
$path:=System folder:C487(Desktop:K41:16)

PROGRESS:=Progress New
Progress SET PROGRESS(PROGRESS; -1)
Progress SET BUTTON ENABLED(PROGRESS; True:C214)
Progress SET ON STOP METHOD(PROGRESS; "CB_STOP")

<>STOP:=False:C215

$size:=Get folder size($path; "CB")

Progress QUIT(PROGRESS)
```

`CB.4dm` (the callback method named above):
```4d
C_REAL:C285($1)  //size
C_BOOLEAN:C305($0)  //true to abort

Progress SET TITLE(PROGRESS; String:C10($1))

$0:=<>STOP
```

`CB_STOP.4dm` (wired up via `Progress SET ON STOP METHOD`, runs if the user clicks the progress bar's stop button):
```4d
<>STOP:=True:C214
```

A variation using only the callback itself, with no progress-bar component — abort once the running total passes a fixed size, and keep no dependency beyond what `Get folder size` requires:

```4d
 // callback method, e.g. "ABORT_IF_TOO_BIG"
C_REAL:C285($1)  //size so far
C_BOOLEAN:C305($0)  //true to abort

$0:=($1>2*1024*1024*1024)  //stop once we've counted more than 2 GB
```

---

## Error handling & troubleshooting

- **A missing or empty `path` returns `0`, not a 4D error.** Check that the folder actually exists before calling, if you need to distinguish "empty folder" from "folder not found."
- **Aborting from the callback discards the running total — the result is `0`, not the partial size.** If you need the size counted before the abort, save `$1` yourself inside the callback before returning `true`.
- **A callback that doesn't return a boolean is silently ignored, not an error.** The scan just keeps going as if no abort was requested.
- **Hidden files, dotfiles, and package/bundle contents all count toward the total** on both platforms — there's no way to exclude them from the plugin side.
- **On Windows, a symlinked or junctioned subfolder is followed, with no cycle protection.** Avoid pointing `path` at trees containing self-referential symlinks/junctions until this has been verified against your setup.
- **"Size" is logical byte count, not "size on disk."** Don't expect it to match a filesystem's allocated/rounded block size.
- **Callback/progress-check frequency is item-count-based (every 8192 entries), not time-based.** A folder with very few, very large files will call back rarely even if the scan takes a long time; a folder with millions of tiny files will call back very often.

---

## Quick reference

```4d
 // simple call, no callback
$path:=System folder:C487(Desktop:K41:16)
$size:=Get folder size($path)

 // with a callback that can abort
C_REAL($size)
$path:=System folder:C487(Desktop:K41:16)
$size:=Get folder size($path; "ABORT_IF_TOO_BIG")
```

```4d
 // ABORT_IF_TOO_BIG
C_REAL:C285($1)
C_BOOLEAN:C305($0)
$0:=($1>2*1024*1024*1024)
```
