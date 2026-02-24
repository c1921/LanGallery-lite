import type { ImageListResponse } from "./types";

export async function fetchImages(): Promise<ImageListResponse> {
  const response = await fetch("/api/images");
  if (!response.ok) {
    throw new Error(`读取图片失败: HTTP ${response.status}`);
  }
  return (await response.json()) as ImageListResponse;
}
