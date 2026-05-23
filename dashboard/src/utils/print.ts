import { router } from "@/router";

export function printMarkdown(markdown: string) {
  if (!markdown) return;
  const printWindow = window.open(
    router.resolve({
        path: '/markdownPrint'
    }
  ).href, '_blank');
  const timer = setInterval(() => {
    printWindow?.postMessage({
      type: 'PrintData.Send',
      data: markdown
    }, '*');
  }, 1000);
  const clear = (e: any) => {
    if (e.data === 'PrintData.Ready') {
      clearInterval(timer);
      window.removeEventListener('message', clear);
    }
  };
  window.addEventListener('message', clear);
}