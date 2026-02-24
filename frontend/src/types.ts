export interface ImageItem {
  id: string;
  name: string;
  rel_path: string;
  mtime: string;
  size: number;
  url: string;
}

export interface ImageListResponse {
  items: ImageItem[];
  total: number;
}
