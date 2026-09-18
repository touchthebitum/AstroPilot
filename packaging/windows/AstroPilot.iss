; Compile through scripts/build_windows_installer.py.
#ifndef AppVersion
  #error AppVersion must be supplied by the installer build script
#endif
#ifndef SourceDir
  #error SourceDir must point to the existing onedir build
#endif
#ifndef InstallerOutputDir
  #error InstallerOutputDir must be supplied by the installer build script
#endif

[Setup]
AppName=AstroPilot
AppVersion={#AppVersion}
; Product identity: never change after the first distributed installation.
AppId={{A3B620CB-8E79-4B91-8DAB-4CF1BEE63985}
DefaultDirName={userpf}\AstroPilot
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
CloseApplications=yes
RestartApplications=yes
UsePreviousAppDir=yes
UninstallDisplayIcon={app}\AstroPilot.exe
OutputDir={#InstallerOutputDir}
OutputBaseFilename=AstroPilot-{#AppVersion}-windows-x86_64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[InstallDelete]
; Retire only AstroPilot distribution metadata left by older onedir payloads.
; Processed before payload copy, which restores metadata supplied by the new build.
; Never target application data or other packages.
Type: filesandordirs; Name: "{app}\_internal\astropilot-*.dist-info"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\AstroPilot"; Filename: "{app}\AstroPilot.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\AstroPilot"; Filename: "{app}\AstroPilot.exe"; WorkingDir: "{app}"; Tasks: desktopicon
