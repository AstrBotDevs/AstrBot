{
  "openapi": "3.1.0",
  "info": {
    "title": "AstrBot Open API",
    "version": "1.0.0",
    "description": "Developer HTTP APIs for AstrBot. Use API Key authentication for /api/v1/* endpoints."
  },
  "servers": [
    {
      "url": "http://localhost:6185"
    }
  ],
  "tags": [
    {
      "name": "Open API",
      "description": "Developer APIs authenticated by API Key"
    }
  ],
  "paths": {
    "/api/v1/im/bots": {
      "get": {
        "tags": [
          "Open API"
        ],
        "summary": "List bot IDs",
        "description": "Returns configured bot/platform IDs.",
        "security": [
          {
            "ApiKeyHeader": []
          }
        ],
        "responses": {
          "200": {
            "description": "OK",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ApiResponseBotList"
                }
              }
            }
          },
          "401": {
            "$ref": "#/components/responses/Unauthorized"
          },
          "403": {
            "$ref": "#/components/responses/Forbidden"
          }
        }
      }
    },
    "/api/v1/file": {
      "post": {
        "tags": [
          "Open API"
        ],
        "summary": "Upload attachment file",
        "description": "Upload a file and get attachment_id for later use in chat/message APIs.",
        "security": [
          {
            "ApiKeyHeader": []
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "multipart/form-data": {
              "schema": {
                "type": "object",
                "required": [
                  "file"
                ],
                "properties": {
                  "file": {
                    "type": "string",
                    "format": "binary"
                  }
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "OK",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ApiResponseUpload"
                }
              }
            }
          },
          "401": {
            "$ref": "#/components/responses/Unauthorized"
          },
          "403": {
            "$ref": "#/components/responses/Forbidden"
          }
        }
      }
    },
    "/api/v1/chat": {
      "post": {
        "tags": [
          "Open API"
        ],
        "summary": "Send chat message (SSE)",
        "description": "Send message to AstrBot chat pipeline and receive streaming SSE response. Reuses /api/chat/send behavior. If session_id/conversation_id is omitted, server will create a new UUID session_id.",
        "security": [
          {
            "ApiKeyHeader": []
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/ChatSendRequest"
              },
              "examples": {
                "plain": {
                  "value": {
                    "message": "Hello",
                    "username": "alice",
                    "session_id": "my_session_001",
                    "enable_streaming": true
                  }
                },
                "multipartMessage": {
                  "value": {
                    "message": [
                      {
                        "type": "plain",
                        "text": "Please analyze this file"
                      },
                      {
                        "type": "file",
                        "attachment_id": "9a2f8c72-e7af-4c0e-b352-111111111111"
                      }
                    ],
                    "username": "alice",
                    "session_id": "my_session_001",
                    "selected_provider": "openai_chat_completion",
                    "selected_model": "gpt-4.1-mini",
                    "enable_streaming": true
                  }
                },
                "withConfig": {
                  "value": {
                    "message": "Use a specific config for this session",
                    "username": "alice",
                    "session_id": "my_session_001",
                    "config_id": "default",
                    "enable_streaming": true
                  }
                },
                "autoSessionWithUsername": {
                  "value": {
                    "message": "hello",
                    "username": "alice",
                    "enable_streaming": true
                  }
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "SSE stream",
            "content": {
              "text/event-stream": {
                "schema": {
                  "type": "string"
                }
              }
            }
          },
          "401": {
            "$ref": "#/components/responses/Unauthorized"
          },
          "403": {
            "$ref": "#/components/responses/Forbidden"
          }
        }
      }
    },
    "/api/v1/chat/sessions": {
      "get": {
        "tags": [
          "Open API"
        ],
        "summary": "List chat sessions with pagination",
        "description": "List chat sessions for the specified username.",
        "security": [
          {
            "ApiKeyHeader": []
          }
        ],
        "parameters": [
          {
            "name": "page",
            "in": "query",
            "schema": {
              "type": "integer",
              "default": 1,
              "minimum": 1
            }
          },
          {
            "name": "page_size",
            "in": "query",
            "schema": {
              "type": "integer",
              "default": 20,
              "minimum": 1,
              "maximum": 100
            }
          },
          {
            "name": "platform_id",
            "in": "query",
            "schema": {
              "type": "string"
            },
            "description": "Optional platform filter"
          },
          {
            "name": "username",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string"
            },
            "description": "Target username."
          }
        ],
        "responses": {
          "200": {
            "description": "OK",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ApiResponseChatSessions"
                }
              }
            }
          },
          "401": {
            "$ref": "#/components/responses/Unauthorized"
          },
          "403": {
            "$ref": "#/components/responses/Forbidden"
          }
        }
      }
    },
    "/api/v1/im/message": {
      "post": {
        "tags": [
          "Open API"
        ],
        "summary": "Send proactive message to a platform bot",
        "description": "Send message directly to platform bot by umo + message chain payload.",
        "security": [
          {
            "ApiKeyHeader": []
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/SendMessageRequest"
              },
              "examples": {
                "plain": {
                  "value": {
                    "umo": "webchat:FriendMessage:openapi_probe",
                    "message": "ping from api key"
                  }
                },
                "chain": {
                  "value": {
                    "umo": "webchat:FriendMessage:openapi_probe",
                    "message": [
                      {
                        "type": "plain",
                        "text": "hello"
                      },
                      {
                        "type": "image",
                        "attachment_id": "9a2f8c72-e7af-4c0e-b352-111111111111"
                      }
                    ]
                  }
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "OK",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ApiResponseEmpty"
                }
              }
            }
          },
          "401": {
            "$ref": "#/components/responses/Unauthorized"
          },
          "403": {
            "$ref": "#/components/responses/Forbidden"
          }
        }
      }
    },
    "/api/v1/configs": {
      "get": {
        "tags": [
          "Open API"
        ],
        "summary": "List available chat config files",
        "description": "Returns all available AstrBot config files that can be selected by Chat API using config_id/config_name.",
        "security": [
          {
            "ApiKeyHeader": []
          }
        ],
        "responses": {
          "200": {
            "description": "OK",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ApiResponseChatConfigList"
                }
              }
            }
          },
          "401": {
            "$ref": "#/components/responses/Unauthorized"
          },
          "403": {
            "$ref": "#/components/responses/Forbidden"
          }
        }
      }
    }
  },
  "components": {
    "securitySchemes": {
      "ApiKeyHeader": {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "Open API key. Authorization: Bearer <api_key> is also accepted."
      }
    },
    "responses": {
      "Unauthorized": {
        "description": "Unauthorized"
      },
      "Forbidden": {
        "description": "Forbidden"
      }
    },
    "schemas": {
      "ApiResponseEmpty": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "example": "ok"
          },
          "message": {
            "type": [
              "string",
              "null"
            ]
          },
          "data": {
            "type": "object",
            "additionalProperties": true
          }
        }
      },
      "ApiResponseBotList": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "example": "ok"
          },
          "message": {
            "type": [
              "string",
              "null"
            ]
          },
          "data": {
            "type": "object",
            "properties": {
              "bot_ids": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              }
            }
          }
        }
      },
      "ApiResponseUpload": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "example": "ok"
          },
          "message": {
            "type": [
              "string",
              "null"
            ]
          },
          "data": {
            "type": "object",
            "properties": {
              "attachment_id": {
                "type": "string"
              },
              "filename": {
                "type": "string"
              },
              "type": {
                "type": "string"
              }
            }
          }
        }
      },
      "ApiResponseChatSessions": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "example": "ok"
          },
          "message": {
            "type": [
              "string",
              "null"
            ]
          },
          "data": {
            "type": "object",
            "properties": {
              "sessions": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/ChatSessionItem"
                }
              },
              "page": {
                "type": "integer"
              },
              "page_size": {
                "type": "integer"
              },
              "total": {
                "type": "integer"
              }
            }
          }
        }
      },
      "ChatSessionItem": {
        "type": "object",
        "properties": {
          "session_id": {
            "type": "string"
          },
          "platform_id": {
            "type": "string"
          },
          "creator": {
            "type": "string"
          },
          "display_name": {
            "type": [
              "string",
              "null"
            ]
          },
          "is_group": {
            "type": "integer"
          },
          "created_at": {
            "type": "string",
            "format": "date-time"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time"
          }
        }
      },
      "MessagePart": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "plain",
              "reply",
              "image",
              "record",
              "file",
              "video"
            ]
          },
          "text": {
            "type": "string"
          },
          "message_id": {
            "type": [
              "string",
              "integer"
            ]
          },
          "selected_text": {
            "type": "string"
          },
          "attachment_id": {
            "type": "string"
          },
          "filename": {
            "type": "string"
          },
          "path": {
            "type": "string"
          }
        },
        "required": [
          "type"
        ]
      },
      "ChatSendRequest": {
        "type": "object",
        "required": [
          "message",
          "username"
        ],
        "properties": {
          "message": {
            "oneOf": [
              {
                "type": "string"
              },
              {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/MessagePart"
                }
              }
            ]
          },
          "session_id": {
            "type": "string",
            "description": "Optional chat session ID. If omitted (and conversation_id is also omitted), server creates a UUID automatically."
          },
          "conversation_id": {
            "type": "string",
            "description": "Alias of session_id."
          },
          "username": {
            "type": "string",
            "description": "Target username."
          },
          "selected_provider": {
            "type": "string"
          },
          "selected_model": {
            "type": "string"
          },
          "enable_streaming": {
            "type": "boolean",
            "default": true
          },
          "config_id": {
            "type": "string",
            "description": "Optional AstrBot config file ID. If provided, the chat session will use this config file. Use \"default\" to reset to default config."
          },
          "config_name": {
            "type": "string",
            "description": "Optional AstrBot config file name. Used only when config_id is not provided."
          }
        }
      },
      "SendMessageRequest": {
        "type": "object",
        "required": [
          "umo",
          "message"
        ],
        "properties": {
          "umo": {
            "type": "string",
            "description": "Unified message origin. Format: platform:message_type:session_id"
          },
          "message": {
            "oneOf": [
              {
                "type": "string"
              },
              {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/MessagePart"
                }
              }
            ]
          }
        }
      },
      "ChatConfigFile": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          },
          "name": {
            "type": "string"
          },
          "path": {
            "type": "string"
          },
          "is_default": {
            "type": "boolean"
          }
        },
        "required": [
          "id",
          "name",
          "path",
          "is_default"
        ]
      },
      "ApiResponseChatConfigList": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "example": "ok"
          },
          "message": {
            "type": [
              "string",
              "null"
            ]
          },
          "data": {
            "type": "object",
            "properties": {
              "configs": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/ChatConfigFile"
                }
              }
            }
          }
        }
      }
    }
  }
}
