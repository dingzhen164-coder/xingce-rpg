package com.xingce.xiuxian;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;

import java.io.File;
import java.io.FileNotFoundException;

/** 把下好的更新包（缓存目录里的 update.apk）交给系统安装器读。只读、只这一个文件。 */
public class ApkProvider extends ContentProvider {
    static final String AUTHORITY = "com.xingce.xiuxian.apk";
    static final Uri URI = Uri.parse("content://" + AUTHORITY + "/update.apk");

    static File file(android.content.Context c) { return new File(c.getCacheDir(), "update.apk"); }

    @Override public boolean onCreate() { return true; }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        return ParcelFileDescriptor.open(file(getContext()), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override public String getType(Uri uri) { return "application/vnd.android.package-archive"; }
    @Override public Cursor query(Uri u, String[] p, String s, String[] a, String o) { return null; }
    @Override public Uri insert(Uri u, ContentValues v) { return null; }
    @Override public int delete(Uri u, String s, String[] a) { return 0; }
    @Override public int update(Uri u, ContentValues v, String s, String[] a) { return 0; }
}
