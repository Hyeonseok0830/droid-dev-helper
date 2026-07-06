import os
import sys
import shutil
import glob
import subprocess
from PIL import Image

def generate_assets(source_icon, assets_dir):
    os.makedirs(assets_dir, exist_ok=True)
    img = Image.open(source_icon)
    
    # Required MSIX asset sizes
    sizes = {
        "StoreLogo.png": (50, 50),
        "Square150x150Logo.png": (150, 150),
        "Square44x44Logo.png": (44, 44),
        "Wide310x150Logo.png": (310, 150),
        "SplashScreen.png": (620, 300)
    }
    
    for filename, size in sizes.items():
        out_path = os.path.join(assets_dir, filename)
        resized = img.copy()
        if size[0] != size[1]:
            bg = Image.new("RGBA", size, (15, 23, 42, 255))
            icon_h = int(size[1] * 0.7)
            icon_w = icon_h
            icon_resized = img.resize((icon_w, icon_h), Image.Resampling.LANCZOS)
            offset = ((size[0] - icon_w) // 2, (size[1] - icon_h) // 2)
            bg.paste(icon_resized, offset, icon_resized if icon_resized.mode == 'RGBA' else None)
            bg.save(out_path)
        else:
            resized.thumbnail(size, Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", size, (0, 0, 0, 0))
            offset = ((size[0] - resized.width) // 2, (size[1] - resized.height) // 2)
            canvas.paste(resized, offset)
            canvas.save(out_path)
            
    print("Generated all package assets successfully.")

def write_manifest(manifest_path, version):
    parts = version.replace('v', '').split('.')
    while len(parts) < 4:
        parts.append('0')
    quad_version = '.'.join(parts[:4])
    
    manifest_content = f"""<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
         IgnorableNamespaces="uap rescap">
  <Identity Name="Hyeonseok0830.DroidDevHelper"
            Publisher="CN=Hyeonseok0830"
            Version="{quad_version}"
            ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>Droid Dev Helper</DisplayName>
    <PublisherDisplayName>Hyeonseok0830</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Universal" MinVersion="10.0.17763.0" MaxVersionTested="10.0.19041.0" />
  </Dependencies>
  <Resources>
    <Resource Language="ko-KR" />
    <Resource Language="en-US" />
  </Resources>
  <Applications>
    <Application Id="App"
                 Executable="droid-dev-helper.exe"
                 EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="Droid Dev Helper"
                          Description="Android Developer Helper Tool utilizing ADB and Scrcpy."
                          BackgroundColor="#0f172a"
                          Square150x150Logo="Assets\\Square150x150Logo.png"
                          Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png" />
        <uap:SplashScreen Image="Assets\\SplashScreen.png" />
      </uap:VisualElements>
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""
    with open(manifest_path, 'w', encoding='utf-8') as f:
        f.write(manifest_content)
    print(f"AppXManifest.xml generated with version: {quad_version}")

def find_makeappx():
    paths = glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\makeappx.exe")
    if not paths:
        paths = glob.glob(r"C:\Program Files (x86)\Windows Kits\10\App Certification Kit\makeappx.exe")
    if not paths:
        raise FileNotFoundError("MakeAppx.exe could not be found in Windows Kits paths.")
    
    paths.sort()
    return paths[-1]

def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "1.0.0.0"
    layout_dir = "AppxLayout"
    assets_dir = os.path.join(layout_dir, "Assets")
    
    if os.path.exists(layout_dir):
        shutil.rmtree(layout_dir)
    os.makedirs(layout_dir)
    
    exe_source = r"dist\droid-dev-helper.exe"
    if not os.path.exists(exe_source):
        print(f"Error: Compiled binary not found at {exe_source}. Please build with PyInstaller first.")
        sys.exit(1)
        
    shutil.copy(exe_source, os.path.join(layout_dir, "droid-dev-helper.exe"))
    shutil.copy("droid-dev-helper.png", os.path.join(layout_dir, "droid-dev-helper.png"))
    
    generate_assets("droid-dev-helper.png", assets_dir)
    write_manifest(os.path.join(layout_dir, "AppXManifest.xml"), version)
    
    makeappx_exe = find_makeappx()
    print(f"Found MakeAppx.exe: {makeappx_exe}")
    
    out_msix = f"dist\\Droid_Dev_Helper_{version}.msix"
    cmd = [makeappx_exe, "pack", "/d", layout_dir, "/p", out_msix, "/o"]
    
    print(f"Executing packaging: {' '.join(cmd)}")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode == 0:
        print(f"MSIX Package created successfully at: {out_msix}")
    else:
        print("Error during packaging:")
        print(res.stderr or res.stdout)
        sys.exit(res.returncode)

if __name__ == "__main__":
    main()
