import axios from 'axios';

// Conversations
export async function listConversations() {
  const res = await axios.get('/api/chat/conversations');
  return res.data?.data;
}

export async function getConversation(conversation_id: string) {
  const res = await axios.get(`/api/chat/get_conversation`, {
    params: { conversation_id },
  });
  return res.data?.data;
}

export async function newConversation() {
  const res = await axios.get('/api/chat/new_conversation');
  return res.data?.data;
}

export async function deleteConversation(conversation_id: string) {
  const res = await axios.get('/api/chat/delete_conversation', {
    params: { conversation_id },
  });
  return res.data?.data;
}

export async function renameConversation(conversation_id: string, title: string) {
  const res = await axios.post('/api/chat/rename_conversation', {
    conversation_id,
    title,
  });
  return res.data?.data;
}

// Media
export async function postImage(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await axios.post('/api/chat/post_image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data?.data;
}

export async function postFile(file: Blob | File) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await axios.post('/api/chat/post_file', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data?.data;
}

export async function getFile(filename: string): Promise<Blob> {
  const res = await axios.get('/api/chat/get_file', {
    params: { filename },
    responseType: 'blob',
  });
  return res.data as Blob;
}

// Streaming send
export async function sendMessageStream(payload: {
  message: string;
  conversation_id: string;
  image_url: string[];
  audio_url: string[];
  selected_provider?: string;
  selected_model?: string;
}) {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const token = localStorage.getItem('token');
  if (token) headers['Authorization'] = 'Bearer ' + token;

  const response = await fetch('/api/chat/send', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response;
}
