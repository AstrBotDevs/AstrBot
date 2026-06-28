
# AstrBot Knowledge Base

> [!TIP]
> Requires AstrBot version >= 4.5.0.

<img width="1910" height="883" alt="image" src="https://github.com/user-attachments/assets/d1a71afa-04cd-493e-be9c-a6a6cba22274" />

## Configuring Embedding Model

Open the service provider page, click "Add Service Provider", and select Embedding.

Currently, AstrBot supports embedding vector services compatible with OpenAI API and Gemini API.

Click on the provider card above to enter the configuration page and fill in the configuration.

After completing the configuration, click Save.

## Configuring Reranker Model (Optional)

A reranker model can improve the precision of final retrieval results to some extent.

Similar to configuring the embedding model, open the service provider page, click "Add Service Provider", and select Reranker. For more information about reranker models, please refer to online resources.

## Creating a Knowledge Base

AstrBot supports multiple knowledge base management. During chat, you can **freely specify which knowledge base to use**.

Enter the knowledge base page and click "Create Knowledge Base", as shown below:

<img width="1910" height="883" alt="image" src="https://github.com/user-attachments/assets/1832ec2e-5cbb-4d1a-9466-1d10a34d926b" />

Fill in the relevant information. In the embedding model dropdown menu, you will see the embedding model and reranker model you just created (reranker model is optional).

> [!TIP]
> Once you've selected an embedding model for a knowledge base, do not modify the **model** or **vector dimension information** of that provider, as this will **seriously affect** the retrieval accuracy of the knowledge base or even **cause errors**.

## Uploading Files

After creating a knowledge base, you can upload documents to it. Up to 10 files can be uploaded simultaneously, with a maximum size of 128 MB per file.

<img width="1910" height="883" alt="image" src="https://github.com/user-attachments/assets/075a8a8b-0176-4703-b681-e13040ba8082" />

## Using the Knowledge Base

In the configuration file, you can specify different knowledge bases for different configuration profiles.
