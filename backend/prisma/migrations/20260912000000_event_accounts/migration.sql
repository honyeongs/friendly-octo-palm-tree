CREATE TABLE "EventAccount" (
    "userId" TEXT NOT NULL,
    "state" JSONB NOT NULL,
    "revision" INTEGER NOT NULL DEFAULT 0,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "EventAccount_pkey" PRIMARY KEY ("userId")
);
