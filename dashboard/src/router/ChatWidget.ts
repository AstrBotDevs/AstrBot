const ChatWidgetRoutes = {
  path: "/chatwidget",
  component: () => import("@/layouts/blank/BlankLayout.vue"),
  children: [
    {
      name: "ChatWidget",
      path: "/chatwidget",
      component: () => import("@/views/ChatWidget.vue"),
    },
  ],
};

export default ChatWidgetRoutes;
