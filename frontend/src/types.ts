export interface ImageItem {
  id: string;
  name: string;
  rel_path: string;
  mtime: string;
  size: number;
  url: string;
  thumb_url: string;
}

export interface FolderCoverItem {
  id: string;
  name: string;
  rel_dir: string;
  cover: ImageItem;
  image_count: number;
  latest_mtime: string;
}

export interface FolderListResponse {
  items: FolderCoverItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface FolderInfo {
  rel_dir: string;
  name: string;
  total: number;
}

export interface FolderImagesResponse {
  folder: FolderInfo;
  items: ImageItem[];
}
