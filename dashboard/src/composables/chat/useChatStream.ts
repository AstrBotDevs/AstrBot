export type ChatStreamHandlers = {
  onTextStart?: (text: string) => void;
  onTextAppend?: (text: string) => void;
  onImage?: (url: string) => void;
  onAudio?: (url: string) => void;
  onUpdateTitle?: (cid: string, title: string) => void;
  onError?: (err: unknown) => void;
};

export function useChatStream(getMediaUrl: (filename: string) => Promise<string>) {
  async function runStream(body: ReadableStream<Uint8Array> | null, handlers: ChatStreamHandlers = {}) {
    if (!body) return;
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let in_streaming = false;

    while (true) {
      try {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n\n');

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim();
          if (!line) continue;

          let chunk_json: any;
          try {
            chunk_json = JSON.parse(line.replace('data: ', ''));
          } catch (e) {
            console.warn('JSON parse failed:', line, e);
            continue;
          }

          if (!chunk_json || typeof chunk_json !== 'object' || !('type' in chunk_json)) {
            console.warn('Invalid data object:', chunk_json);
            continue;
          }

          const type = chunk_json.type;
          if (type === 'error') {
            handlers.onError?.(chunk_json.data);
            continue;
          }

          if (type === 'image') {
            const img = String(chunk_json.data).replace('[IMAGE]', '');
            const imageUrl = await getMediaUrl(img);
            await handlers.onImage?.(imageUrl);
          } else if (type === 'record') {
            const audio = String(chunk_json.data).replace('[RECORD]', '');
            const audioUrl = await getMediaUrl(audio);
            await handlers.onAudio?.(audioUrl);
          } else if (type === 'plain') {
            if (!in_streaming) {
              handlers.onTextStart?.(chunk_json.data);
              in_streaming = true;
            } else {
              handlers.onTextAppend?.(chunk_json.data);
            }
          } else if (type === 'update_title') {
            handlers.onUpdateTitle?.(chunk_json.cid, chunk_json.data);
          }

          if ((type === 'break' && chunk_json.streaming) || !chunk_json.streaming) {
            in_streaming = false;
          }
        }
      } catch (err) {
        handlers.onError?.(err);
        break;
      }
    }
  }

  return { runStream };
}
