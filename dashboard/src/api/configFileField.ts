import axios from 'axios';

export type FileItem = {
  name: string;
  rel_path: string;
  size: number;
  mtime: number;
};

export async function listFiles(plugin: string, field: string): Promise<FileItem[]> {
  const res = await axios.get(`/api/plugin/${encodeURIComponent(plugin)}/config/filefield/list`, {
    params: { field }
  });
  if (res.data?.status === 'ok') {
    return res.data.data as FileItem[];
  }
  throw new Error(res.data?.message || 'List failed');
}

export async function uploadFile(plugin: string, field: string, file: File): Promise<{ path: string; size: number; mtime: number }>{
  const form = new FormData();
  form.append('field', field);
  form.append('file', file);
  const res = await axios.post(`/api/plugin/${encodeURIComponent(plugin)}/config/filefield/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  if (res.data?.status === 'ok') {
    return res.data.data as { path: string; size: number; mtime: number };
  }
  throw new Error(res.data?.message || 'Upload failed');
}

export async function deleteFile(plugin: string, field: string, relPath: string): Promise<void> {
  const res = await axios.delete(`/api/plugin/${encodeURIComponent(plugin)}/config/filefield/delete`, {
    params: { field, path: relPath }
  });
  if (res.data?.status === 'ok') {
    return;
  }
  throw new Error(res.data?.message || 'Delete failed');
}

