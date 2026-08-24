//%attributes = {}
$path:=System folder:C487(Desktop:K41:16)

PROGRESS:=Progress New
Progress SET PROGRESS(PROGRESS; -1)
Progress SET BUTTON ENABLED(PROGRESS; True:C214)
Progress SET ON STOP METHOD(PROGRESS; "CB_STOP")

<>STOP:=False:C215

$size:=Get folder size($path; "CB")

Progress QUIT(PROGRESS)