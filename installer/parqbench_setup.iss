; ParqBench Non-Admin Inno Setup Script
; Installs strictly in the current user's profile without requesting Administrator elevation.

#define MyAppName "ParqBench"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "ParqBench"
#define MyAppExeName "ParqBench.exe"

[Setup]
; Unique App ID for uninstallation tracking
AppId={{E6F7A189-9A34-4C21-8F3E-6B786937210E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist\installer
OutputBaseFilename=ParqBench-Setup-x64
SetupIconFile=..\assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
; CRITICAL FOR NON-ADMIN: Runs strictly in current user scope without UAC elevation
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
ChangesAssociations=yes
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "associate"; Description: "Associate .parquet files with ParqBench"; GroupDescription: "File Associations:"

[Files]
Source: "..\dist\ParqBench\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "parqbench.desktop.app.1.0"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "parqbench.desktop.app.1.0"; Tasks: desktopicon

[Registry]
; Non-admin File association under HKCU (Current User only, no admin needed)
Root: HKCU; Subkey: "Software\Classes\.parquet"; ValueType: string; ValueName: ""; ValueData: "ParqBench.ParquetFile"; Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\ParqBench.ParquetFile"; ValueType: string; ValueName: ""; ValueData: "Apache Parquet File"; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\ParqBench.ParquetFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\assets\icon.ico,0"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\ParqBench.ParquetFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
