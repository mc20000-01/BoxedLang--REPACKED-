; BoxedLANG.iss - Inno Setup script
;
; Produces a proper Windows Setup.exe with a GUI wizard, Start Menu
; entries, an uninstaller registered in "Apps & Features", and a
; .bx file association - installing both the BoxedLANG CLI tools
; and the BoxedLANG IDE.
;
; This is a SOURCE script, not a binary. To turn it into
; BoxedLANG-Setup.exe:
;   1. Install Inno Setup (free): https://jrsoftware.org/isdl.php
;   2. Open this file in the Inno Setup Compiler (or run:
;        ISCC.exe BoxedLANG.iss
;      from a Developer/PowerShell prompt)
;   3. The finished installer appears in windows\Output\BoxedLANG-Setup.exe
;
; If you don't want to install Inno Setup, just use install.bat
; instead - it installs everything without any extra tools.

#define MyAppName "BoxedLANG"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "BoxedLANG"
#define MyAppExeIDE "IDE.py"

[Setup]
AppId={{6C1D9C2E-6F2B-4B7B-9C36-BOXEDLANG001}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\BoxedLANG
DefaultGroupName=BoxedLANG
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=BoxedLANG-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ChangesEnvironment=yes
UninstallDisplayIcon={app}\IDE.py

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut for the BoxedLANG IDE"; GroupDescription: "Additional shortcuts:"
Name: "fileassoc";   Description: "Open .bx files with the BoxedLANG IDE"; GroupDescription: "File associations:"
Name: "addpath";     Description: "Add BoxedLANG to my PATH (bx / transpilebx / bxdebug commands)"; GroupDescription: "Command line:"

; Everything this script needs lives one folder up (the repo root).
[Files]
Source: "..\bx.py";           DestDir: "{app}"; Flags: ignoreversion
Source: "..\bxastgen.py";     DestDir: "{app}"; Flags: ignoreversion
Source: "..\bxrunner.py";     DestDir: "{app}"; Flags: ignoreversion
Source: "..\transpilebx.py";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\bxdebug.py";      DestDir: "{app}"; Flags: ignoreversion
Source: "..\IDE.py";          DestDir: "{app}"; Flags: ignoreversion
Source: "..\boxcode\*";       DestDir: "{app}\boxcode"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "launch-ide.bat";     DestDir: "{app}"; Flags: ignoreversion
Source: "bx.cmd";             DestDir: "{app}\bin"; Flags: ignoreversion
Source: "transpilebx.cmd";    DestDir: "{app}\bin"; Flags: ignoreversion
Source: "bxdebug.cmd";        DestDir: "{app}\bin"; Flags: ignoreversion

[Icons]
Name: "{group}\BoxedLANG IDE"; Filename: "pythonw.exe"; Parameters: """{app}\IDE.py"""; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,BoxedLANG}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\BoxedLANG IDE"; Filename: "pythonw.exe"; Parameters: """{app}\IDE.py"""; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; .bx file association -> BoxedLANG IDE
Root: HKCU; Subkey: "Software\Classes\.bx"; ValueType: string; ValueName: ""; ValueData: "BoxedLANG.bxfile"; Tasks: fileassoc; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\BoxedLANG.bxfile"; ValueType: string; ValueName: ""; ValueData: "BoxedLANG Source File"; Tasks: fileassoc; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\BoxedLANG.bxfile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """pythonw.exe"" ""{app}\IDE.py"" ""%1"""; Tasks: fileassoc

; Add {app}\bin to the user PATH
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}\bin"; Tasks: addpath; \
    Check: NeedsAddPath('{app}\bin')

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Warn (non-blocking) if python isn't found on PATH.
  if not Exec('cmd.exe', '/c python --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    MsgBox('Python 3 was not found. BoxedLANG needs Python 3 (with tkinter) ' +
           'from https://python.org/downloads - install it, then run this ' +
           'setup again, or continue and install it afterwards.',
           mbInformation, MB_OK);
  end
  else if ResultCode <> 0 then
  begin
    MsgBox('Python 3 was not found. BoxedLANG needs Python 3 (with tkinter) ' +
           'from https://python.org/downloads - install it, then run this ' +
           'setup again, or continue and install it afterwards.',
           mbInformation, MB_OK);
  end;
end;

[Run]
Filename: "pythonw.exe"; Parameters: """{app}\IDE.py"""; Description: "Launch the BoxedLANG IDE now"; Flags: nowait postinstall skipifsilent
