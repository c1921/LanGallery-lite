<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { fetchFolderImages, fetchFolders } from "./api";
import type { FolderCoverItem, FolderInfo, ImageItem } from "./types";

const PAGE_SIZE = 50;

const viewMode = ref<"folders" | "folderImages">("folders");
const folders = ref<FolderCoverItem[]>([]);
const images = ref<ImageItem[]>([]);
const currentFolder = ref<FolderInfo | null>(null);

const currentPage = ref(1);
const totalPages = ref(0);
const totalFolders = ref(0);

const loading = ref(true);
const loadError = ref("");
const viewerOpen = ref(false);
const activeIndex = ref(0);
const touchStartX = ref(0);
const touchStartY = ref(0);
const touchEndX = ref(0);
const touchEndY = ref(0);
const touching = ref(false);

const SWIPE_MIN_X = 48;
const SWIPE_MAX_Y = 36;

const activeImage = computed(() => images.value[activeIndex.value] ?? null);
const countText = computed(() => {
  if (viewMode.value === "folders") {
    return `${totalFolders.value} 个文件夹`;
  }
  return `${images.value.length} 张`;
});
const pageText = computed(() => {
  const pages = totalPages.value > 0 ? totalPages.value : 1;
  return `第 ${currentPage.value} / ${pages} 页`;
});
const canPrevPage = computed(() => currentPage.value > 1);
const canNextPage = computed(() => currentPage.value < totalPages.value);
const showFolderPager = computed(
  () =>
    !loading.value &&
    !loadError.value &&
    viewMode.value === "folders" &&
    folders.value.length > 0 &&
    totalPages.value > 1,
);
const folderSubtitle = computed(() => {
  if (!currentFolder.value) {
    return "";
  }
  if (currentFolder.value.rel_dir === ".") {
    return "根目录";
  }
  return currentFolder.value.rel_dir;
});

function openViewer(index: number): void {
  activeIndex.value = index;
  viewerOpen.value = true;
  touching.value = false;
}

function closeViewer(): void {
  viewerOpen.value = false;
  touching.value = false;
}

function showPrev(): void {
  if (!images.value.length) {
    return;
  }
  activeIndex.value = (activeIndex.value - 1 + images.value.length) % images.value.length;
}

function showNext(): void {
  if (!images.value.length) {
    return;
  }
  activeIndex.value = (activeIndex.value + 1) % images.value.length;
}

function clearViewer(): void {
  viewerOpen.value = false;
  activeIndex.value = 0;
  touching.value = false;
}

function onViewerTouchStart(event: TouchEvent): void {
  if (!viewerOpen.value || !event.touches.length) {
    return;
  }
  const touch = event.touches.item(0);
  if (!touch) {
    return;
  }
  touchStartX.value = touch.clientX;
  touchStartY.value = touch.clientY;
  touchEndX.value = touch.clientX;
  touchEndY.value = touch.clientY;
  touching.value = true;
}

function onViewerTouchMove(event: TouchEvent): void {
  if (!touching.value || !event.touches.length) {
    return;
  }
  const touch = event.touches.item(0);
  if (!touch) {
    return;
  }
  touchEndX.value = touch.clientX;
  touchEndY.value = touch.clientY;
}

function onViewerTouchEnd(): void {
  if (!touching.value || !viewerOpen.value) {
    return;
  }
  touching.value = false;

  const deltaX = touchEndX.value - touchStartX.value;
  const deltaY = touchEndY.value - touchStartY.value;
  if (Math.abs(deltaX) < SWIPE_MIN_X || Math.abs(deltaY) > SWIPE_MAX_Y) {
    return;
  }
  if (deltaX < 0) {
    showNext();
    return;
  }
  showPrev();
}

async function loadFolderPage(page: number, forceRefresh = false): Promise<void> {
  loading.value = true;
  loadError.value = "";

  try {
    const result = await fetchFolders(page, PAGE_SIZE, forceRefresh);
    viewMode.value = "folders";
    folders.value = result.items;
    currentPage.value = result.page;
    totalPages.value = result.total_pages;
    totalFolders.value = result.total;
    images.value = [];
    currentFolder.value = null;
    clearViewer();
  } catch (error: unknown) {
    folders.value = [];
    totalPages.value = 0;
    totalFolders.value = 0;
    loadError.value = error instanceof Error ? error.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

async function openFolder(folder: FolderCoverItem): Promise<void> {
  loading.value = true;
  loadError.value = "";

  try {
    const result = await fetchFolderImages(folder.rel_dir);
    viewMode.value = "folderImages";
    currentFolder.value = result.folder;
    images.value = result.items;
    clearViewer();
  } catch (error: unknown) {
    images.value = [];
    currentFolder.value = null;
    loadError.value = error instanceof Error ? error.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

async function reloadCurrentFolder(forceRefresh = false): Promise<void> {
  if (!currentFolder.value) {
    return;
  }
  loading.value = true;
  loadError.value = "";

  try {
    const result = await fetchFolderImages(currentFolder.value.rel_dir, forceRefresh);
    currentFolder.value = result.folder;
    images.value = result.items;
    if (!images.value.length) {
      clearViewer();
    } else if (activeIndex.value >= images.value.length) {
      activeIndex.value = 0;
    }
  } catch (error: unknown) {
    images.value = [];
    loadError.value = error instanceof Error ? error.message : "加载失败";
    clearViewer();
  } finally {
    loading.value = false;
  }
}

function backToFolders(): void {
  viewMode.value = "folders";
  images.value = [];
  currentFolder.value = null;
  clearViewer();
}

function refreshCurrentView(): void {
  if (viewMode.value === "folders") {
    void loadFolderPage(currentPage.value, true);
    return;
  }
  void reloadCurrentFolder(true);
}

function goPrevPage(): void {
  if (!canPrevPage.value) {
    return;
  }
  void loadFolderPage(currentPage.value - 1);
}

function goNextPage(): void {
  if (!canNextPage.value) {
    return;
  }
  void loadFolderPage(currentPage.value + 1);
}

function onKeydown(event: KeyboardEvent): void {
  if (!viewerOpen.value) {
    return;
  }

  if (event.key === "Escape") {
    closeViewer();
  } else if (event.key === "ArrowLeft") {
    showPrev();
  } else if (event.key === "ArrowRight") {
    showNext();
  }
}

onMounted(() => {
  window.addEventListener("keydown", onKeydown);
  void loadFolderPage(1);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <main class="page">
    <header class="topbar">
      <div>
        <h1 class="title">LanGallery Lite</h1>
        <p v-if="viewMode === 'folders'" class="subtitle">按文件夹浏览</p>
        <p v-else class="subtitle">{{ currentFolder?.name }} · {{ folderSubtitle }}</p>
      </div>
      <div class="actions">
        <button
          v-if="viewMode === 'folderImages'"
          type="button"
          class="refresh"
          :disabled="loading"
          @click="backToFolders"
        >
          返回文件夹
        </button>
        <span class="count">{{ countText }}</span>
        <button type="button" class="refresh" :disabled="loading" @click="refreshCurrentView">
          刷新
        </button>
      </div>
    </header>

    <nav v-if="showFolderPager" class="pager pager-top mobile-only">
      <button type="button" class="refresh" :disabled="!canPrevPage" @click="goPrevPage">上一页</button>
      <span class="pager-text">{{ pageText }}</span>
      <button type="button" class="refresh" :disabled="!canNextPage" @click="goNextPage">下一页</button>
    </nav>

    <p v-if="loading" class="hint">加载中...</p>
    <p v-else-if="loadError" class="hint error">{{ loadError }}</p>
    <p v-else-if="viewMode === 'folders' && !folders.length" class="hint">目录下没有可显示的文件夹</p>
    <p v-else-if="viewMode === 'folderImages' && !images.length" class="hint">当前文件夹没有可显示图片</p>

    <section v-if="!loading && !loadError && viewMode === 'folders' && folders.length" class="grid folder-grid">
      <button
        v-for="folder in folders"
        :key="folder.id"
        type="button"
        class="card folder-card"
        @click="openFolder(folder)"
      >
        <img :src="folder.cover.thumb_url" :alt="folder.name" loading="lazy" />
        <div class="folder-meta">
          <p class="folder-name">{{ folder.name }}</p>
          <p class="folder-sub">{{ folder.image_count }} 张 · {{ folder.rel_dir }}</p>
        </div>
      </button>
    </section>

    <nav v-if="showFolderPager" class="pager">
      <button type="button" class="refresh" :disabled="!canPrevPage" @click="goPrevPage">上一页</button>
      <span class="pager-text">{{ pageText }}</span>
      <button type="button" class="refresh" :disabled="!canNextPage" @click="goNextPage">下一页</button>
    </nav>

    <section
      v-if="!loading && !loadError && viewMode === 'folderImages' && images.length"
      class="grid image-grid"
    >
      <button
        v-for="(item, index) in images"
        :key="item.id"
        type="button"
        class="card"
        @click="openViewer(index)"
      >
        <img :src="item.thumb_url" :alt="item.name" loading="lazy" />
      </button>
    </section>
  </main>

  <div
    v-if="viewerOpen && activeImage"
    class="viewer"
    @click.self="closeViewer"
    @touchstart.passive="onViewerTouchStart"
    @touchmove.passive="onViewerTouchMove"
    @touchend="onViewerTouchEnd"
  >
    <header class="viewer-top">
      <p class="viewer-meta">
        {{ activeIndex + 1 }} / {{ images.length }} · {{ activeImage.name }}
      </p>
      <button type="button" class="viewer-btn" @click="closeViewer">关闭</button>
    </header>

    <div class="viewer-body">
      <img class="viewer-image" :src="activeImage.url" :alt="activeImage.name" />
    </div>

    <footer class="viewer-actions">
      <button type="button" class="viewer-btn" @click="showPrev">上一张</button>
      <button type="button" class="viewer-btn" @click="showNext">下一张</button>
    </footer>
  </div>
</template>
