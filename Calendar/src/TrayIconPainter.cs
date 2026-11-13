using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.IO;

namespace KKCalendar
{
    /// <summary>托盘图标：一页小日历，上面写今天几号。按托盘图标的实际像素尺寸现画，不缩放。</summary>
    internal static class TrayIconPainter
    {
        public static Bitmap Render(int day, int size, bool lightTaskbar, bool holiday)
        {
            var ink = lightTaskbar ? Color.FromArgb(0x1C, 0x1C, 0x1C) : Color.FromArgb(0xF4, 0xF4, 0xF4);
            var red = lightTaskbar ? Color.FromArgb(0xC9, 0x2A, 0x2F) : Color.FromArgb(0xFF, 0x7A, 0x7A);
            var bitmap = new Bitmap(size, size, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(bitmap))
            {
                g.Clear(Color.Transparent);
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;

                float s = size;
                float stroke = Math.Max(1f, (float)Math.Round(s / 16f));
                float inset = stroke / 2f;
                var page = new RectangleF(inset, s * 0.08f + inset, s - stroke, s * 0.92f - stroke);
                float radius = Math.Max(2f, s * 0.16f);

                // 页眉：一条实心的顶边，像撕页日历
                float headerH = Math.Max(2f, (float)Math.Round(s * 0.2f));
                using (var path = Rounded(new RectangleF(page.X, page.Y, page.Width, headerH + radius), radius))
                using (var brush = new SolidBrush(holiday ? red : ink))
                {
                    var clip = g.Clip;
                    g.SetClip(new RectangleF(0, 0, s, page.Y + headerH));
                    g.FillPath(brush, path);
                    g.Clip = clip;
                }
                using (var path = Rounded(page, radius))
                using (var pen = new Pen(ink, stroke))
                    g.DrawPath(pen, path);

                // 日期数字：在页眉下面的区域里居中，尽量大
                var area = new RectangleF(page.X + stroke, page.Y + headerH, page.Width - stroke * 2,
                                          page.Bottom - page.Y - headerH - stroke);
                DrawNumber(g, day.ToString(), area, holiday ? red : ink);
            }
            return bitmap;
        }

        static void DrawNumber(Graphics g, string text, RectangleF area, Color color)
        {
            using (var family = PickFamily())
            using (var path = new GraphicsPath())
            {
                // 先用 100 的字号排出轮廓，再按实际可用空间缩放：数字紧贴区域，不受字体行距影响
                path.AddString(text, family, (int)FontStyle.Bold, 100f, PointF.Empty, StringFormat.GenericTypographic);
                var bounds = path.GetBounds();
                float scale = Math.Min(area.Width * 0.92f / bounds.Width, area.Height * 0.78f / bounds.Height);
                using (var matrix = new Matrix())
                {
                    matrix.Translate(area.X + area.Width / 2f, area.Y + area.Height / 2f + area.Height * 0.02f);
                    matrix.Scale(scale, scale);
                    matrix.Translate(-(bounds.X + bounds.Width / 2f), -(bounds.Y + bounds.Height / 2f));
                    path.Transform(matrix);
                }
                using (var brush = new SolidBrush(color))
                    g.FillPath(brush, path);
            }
        }

        static FontFamily PickFamily()
        {
            foreach (var name in new[] { "Segoe UI Variable Display", "Segoe UI", "Arial" })
            {
                try { return new FontFamily(name); }
                catch (ArgumentException) { }
            }
            return new FontFamily(GenericFontFamilies.SansSerif);
        }

        static GraphicsPath Rounded(RectangleF r, float radius)
        {
            float d = radius * 2;
            var path = new GraphicsPath();
            path.AddArc(r.X, r.Y, d, d, 180, 90);
            path.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            path.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            path.CloseFigure();
            return path;
        }

        /// <summary>
        /// 把 32 位 ARGB 位图包成 .ico 再交给 Icon，保证半透明边缘不丢
        /// （Bitmap.GetHicon 会把 alpha 弄坏）。
        /// </summary>
        public static Icon ToIcon(Bitmap bitmap)
        {
            int w = bitmap.Width, h = bitmap.Height;
            int maskStride = ((w + 31) / 32) * 4;
            int pixelBytes = w * h * 4;
            int imageBytes = 40 + pixelBytes + maskStride * h;

            using (var stream = new MemoryStream())
            using (var writer = new BinaryWriter(stream))
            {
                // ICONDIR
                writer.Write((short)0);
                writer.Write((short)1);
                writer.Write((short)1);
                // ICONDIRENTRY
                writer.Write((byte)(w >= 256 ? 0 : w));
                writer.Write((byte)(h >= 256 ? 0 : h));
                writer.Write((byte)0);
                writer.Write((byte)0);
                writer.Write((short)1);
                writer.Write((short)32);
                writer.Write(imageBytes);
                writer.Write(6 + 16);
                // BITMAPINFOHEADER（高度要写两倍：颜色 + 掩码）
                writer.Write(40);
                writer.Write(w);
                writer.Write(h * 2);
                writer.Write((short)1);
                writer.Write((short)32);
                writer.Write(0);
                writer.Write(pixelBytes + maskStride * h);
                writer.Write(0);
                writer.Write(0);
                writer.Write(0);
                writer.Write(0);

                var data = bitmap.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
                try
                {
                    var row = new byte[w * 4];
                    for (int y = h - 1; y >= 0; y--)          // 自下而上
                    {
                        System.Runtime.InteropServices.Marshal.Copy(data.Scan0 + y * data.Stride, row, 0, row.Length);
                        writer.Write(row);
                    }
                }
                finally
                {
                    bitmap.UnlockBits(data);
                }
                writer.Write(new byte[maskStride * h]);       // 全 0：完全靠 alpha
                writer.Flush();
                stream.Position = 0;
                return new Icon(stream, w, h);
            }
        }
    }
}
