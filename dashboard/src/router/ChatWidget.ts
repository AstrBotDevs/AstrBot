const ChatWidgetRoutes = {
  path: "/chatwidget",
  component: () => import("@/layouts/blank/BlankLayout.vue"),
  children: [
    {
      name: "ChatWidget",
      path: "",
      component: () => import("@/views/ChatWidget.vue"),
    },
    {
      name: "MarkdownPrit",
      path: "/markdownPrint",
      component: () => import("@/views/print.vue"),
    }
  ],
};

export default ChatWidgetRoutes;
