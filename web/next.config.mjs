/** 정적 사이트: `npm run build` → out/. 데이터는 public/data (pipeline/sillok/export.py가 만든다) */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};
export default nextConfig;
