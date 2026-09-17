On Error Resume Next

' Avvio nascosto Script2 - nessuna finestra visibile
base = "C:\Users\alecl\Desktop\script2\"
py   = "C:\Users\alecl\AppData\Local\Programs\Python\Python313\python.exe"
cf   = "C:\Users\alecl\AppData\Local\Temp\opencode\cloudflared.exe"
logfile = "C:\Users\alecl\AppData\Local\Temp\opencode\cf_bat.log"

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

' 1) Pulisce il vecchio log del tunnel
If fso.FileExists(logfile) Then fso.DeleteFile logfile

' 2) Avvia Flask nascosto
sh.CurrentDirectory = base
sh.Run """" & py & """ app.py", 0, False

' 3) Avvia il tunnel Cloudflare nascosto con log su file
sh.Run """" & cf & """ tunnel --url http://localhost:5000 --no-autoupdate --logfile """ & logfile & """ --loglevel info", 0, False

' 4) Aspetta che il tunnel generi il link
WScript.Sleep 15000

' 5) Legge il link dal log
link = ""
If fso.FileExists(logfile) Then
    Set f = fso.OpenTextFile(logfile, 1)
    Do Until f.AtEndOfStream
        line = f.ReadLine
        p = InStr(line, "https://")
        If p > 0 Then
            resto = Mid(line, p)
            sp = InStr(resto, " ")
            If sp > 0 Then resto = Left(resto, sp - 1)
            If InStr(resto, "trycloudflare.com") > 0 Then link = resto
        End If
    Loop
    f.Close
End If

If link <> "" Then
    ' 6) Aggiorna il redirect su GitHub (push nascosto)
    sh.Run """" & py & """ update_redirect.py """ & link & """", 0, True
End If