Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @"
using System; using System.Drawing; using System.Drawing.Imaging; using System.Runtime.InteropServices;
public static class LogoPrep {
  public static int[] Bbox(Bitmap b){
    var r=new Rectangle(0,0,b.Width,b.Height); var d=b.LockBits(r,ImageLockMode.ReadOnly,PixelFormat.Format32bppArgb);
    int minX=b.Width,minY=b.Height,maxX=0,maxY=0; byte[] buf=new byte[d.Stride*b.Height]; Marshal.Copy(d.Scan0,buf,0,buf.Length); b.UnlockBits(d);
    for(int y=0;y<b.Height;y++)for(int x=0;x<b.Width;x++){ if(buf[y*d.Stride+x*4+3]>40){ if(x<minX)minX=x; if(x>maxX)maxX=x; if(y<minY)minY=y; if(y>maxY)maxY=y; } }
    return new int[]{minX,minY,maxX,maxY};
  }
  public static Bitmap CropScale(Bitmap b,int x,int y,int w,int h,int outW,int outH,int dx,int dy,int dw,int dh){
    var o=new Bitmap(outW,outH,PixelFormat.Format32bppArgb); using(var g=Graphics.FromImage(o)){
      g.InterpolationMode=System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic; g.SmoothingMode=System.Drawing.Drawing2D.SmoothingMode.HighQuality; g.PixelOffsetMode=System.Drawing.Drawing2D.PixelOffsetMode.HighQuality;
      g.DrawImage(b,new Rectangle(dx,dy,dw,dh),new Rectangle(x,y,w,h),GraphicsUnit.Pixel);} return o; }
}
"@
$src = [System.Drawing.Bitmap]::FromFile("e:\sol\frontendv2\logo\Sol-testlogo.png")
$bb = [LogoPrep]::Bbox($src)
"bbox: " + ($bb -join ",")
$w = $bb[2] - $bb[0] + 1
$h = $bb[3] - $bb[1] + 1
New-Item -ItemType Directory -Force "e:\sol\frontendv2\public" | Out-Null

# wordmark, tightly cropped, transparent background
$outW = 720
$outH = [int][math]::Round($outW * $h / $w)
$o = [LogoPrep]::CropScale($src, $bb[0], $bb[1], $w, $h, $outW, $outH, 0, 0, $outW, $outH)
$o.Save("e:\sol\frontendv2\public\sol-logo.png", [System.Drawing.Imaging.ImageFormat]::Png)
$o.Dispose()

# square favicon, logo centred with padding
$inner = 224
$fh = [int][math]::Round($inner * $h / $w)
$fy = [int][math]::Round((256 - $fh) / 2)
$f = [LogoPrep]::CropScale($src, $bb[0], $bb[1], $w, $h, 256, 256, 16, $fy, $inner, $fh)
$f.Save("e:\sol\frontendv2\public\favicon.png", [System.Drawing.Imaging.ImageFormat]::Png)
$f.Dispose()
$src.Dispose()
"wordmark ${outW}x${outH}  (source crop ${w}x${h})"
