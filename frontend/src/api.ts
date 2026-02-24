import type { FolderImagesResponse, FolderListResponse } from "./types";

function encodePath(path: string): string {
  return path
    .split("/")
    .filter((segment) => segment.length > 0)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

export async function fetchFolders(
  page: number,
  pageSize = 50,
  forceRefresh = false,
  query = "",
): Promise<FolderListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (forceRefresh) {
    params.set("refresh", "true");
  }
  const normalizedQuery = query.trim();
  if (normalizedQuery) {
    params.set("q", normalizedQuery);
  }

  const response = await fetch(`/api/images?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`读取文件夹失败: HTTP ${response.status}`);
  }
  return (await response.json()) as FolderListResponse;
}

export async function fetchFolderImages(
  relDir: string,
  forceRefresh = false,
): Promise<FolderImagesResponse> {
  const normalized = relDir === "." ? "%2E" : encodePath(relDir);
  const refreshQuery = forceRefresh ? "?refresh=true" : "";
  const response = await fetch(`/api/images/${normalized}${refreshQuery}`);
  if (!response.ok) {
    throw new Error(`读取目录图片失败: HTTP ${response.status}`);
  }
  return (await response.json()) as FolderImagesResponse;
}
