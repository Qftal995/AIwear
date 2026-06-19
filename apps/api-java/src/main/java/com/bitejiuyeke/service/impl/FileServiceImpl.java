package com.bitejiuyeke.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.bitejiuyeke.dto.request.EditImageRequest;
import com.bitejiuyeke.dto.request.MergeImageRequest;
import com.bitejiuyeke.dto.request.SearchImageRequest;
import com.bitejiuyeke.dto.response.EditImageResponse;
import com.bitejiuyeke.dto.response.MergeImageResponse;
import com.bitejiuyeke.dto.response.SearchImageResponse;
import com.bitejiuyeke.dto.response.UploadImageResponse;
import com.bitejiuyeke.entity.ImageFile;
import com.bitejiuyeke.mapper.ImageFileMapper;
import com.bitejiuyeke.service.FileService;
import com.bitejiuyeke.service.OssService;
import com.bitejiuyeke.service.PythonImageService;
import com.bitejiuyeke.service.RecordService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;

@Slf4j
@Service
public class FileServiceImpl implements FileService {

    @Autowired
    private ImageFileMapper imageFileMapper;

    private static final long MAX_FILE_SIZE = 52_428_800L;

    @Autowired
    private PythonImageService pythonImageService;

    @Value("${file.upload.dir:uploads}")
    private String uploadBaseDir;

    @Value("${app.public-url:http://localhost:8081}")
    private String appPublicUrl;

    @Autowired
    private RecordService recordService;

    @Autowired
    private OssService ossService;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public UploadImageResponse uploadImage(MultipartFile file, Long userId) {
        if (file == null) {
            throw new RuntimeException("缺少上传文件");
        }
        if (file.isEmpty()) {
            throw new RuntimeException("上传文件为空");
        }
        if (file.getContentType() == null || !file.getContentType().startsWith("image/")) {
            throw new RuntimeException("仅支持图片上传");
        }
        long fileSize = file.getSize();
        if (fileSize > MAX_FILE_SIZE) {
            throw new RuntimeException("图片大小超过限制");
        }

        String originalFileName = file.getOriginalFilename();
        if (originalFileName == null || originalFileName.isBlank()) {
            originalFileName = "image";
        }

        String extension = getFileExtension(originalFileName, file.getContentType());
        String uuid = UUID.randomUUID().toString().replace("-", "");

        Path localDir = Paths.get(uploadBaseDir, "images");
        try {
            Files.createDirectories(localDir);
        } catch (Exception e) {
            throw new RuntimeException("创建本地存储目录失败");
        }

        String finalLocalFileName = uuid + extension;
        Path localFilePath = localDir.resolve(finalLocalFileName);

        try {
            file.transferTo(localFilePath);
            if (!pythonImageService.validateImage(localFilePath)) {
                throw new RuntimeException("图片审核不通过！");
            }

            String url;
            if (ossService.isEnabled()) {
                String objectName = "aiwear/images/" + finalLocalFileName;
                try (var is = Files.newInputStream(localFilePath)) {
                    url = ossService.upload(objectName, is, file.getContentType());
                }
                if (url == null) {
                    url = appPublicUrl + "/uploads/images/" + finalLocalFileName;
                }
            } else {
                url = appPublicUrl + "/uploads/images/" + finalLocalFileName;
            }

            pythonImageService.uploadImage(userId, url);

            ImageFile record = new ImageFile();
            record.setUserId(userId);
            record.setFileName(originalFileName);
            record.setFileSize(fileSize);
            record.setOssUrl(url);
            imageFileMapper.insert(record);

            UploadImageResponse response = new UploadImageResponse();
            response.setUrl(url);
            response.setFileName(originalFileName);
            response.setFileSize(fileSize);
            return response;
        } catch (Exception e) {
            log.error("图片上传失败，原因：{}", e.getMessage());
            throw new RuntimeException(e.getMessage());
        }
    }

    @Override
    public List<ImageFile> myImages(Long userId) {
        LambdaQueryWrapper<ImageFile> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(ImageFile::getUserId, userId).orderByDesc(ImageFile::getId);
        return imageFileMapper.selectList(queryWrapper);
    }

    @Override
    public List<SearchImageResponse> search(Long userId, SearchImageRequest searchImageRequest) {
        List<ImageFile> imageFiles = myImages(userId);
        Map<String, String> map = new HashMap<>();
        for (ImageFile imageFile : imageFiles) {
            map.put(imageFile.getOssUrl(), imageFile.getFileName());
        }
        List<SearchImageResponse> searchImageResponseList = pythonImageService.search(userId, searchImageRequest);
        for (SearchImageResponse searchImageResponse : searchImageResponseList) {
            searchImageResponse.setFileName(map.get(searchImageResponse.getFilePath()));
        }
        return searchImageResponseList;
    }

    @Override
    public EditImageResponse edit(Long userId, EditImageRequest editImageRequest) {
        List<ImageFile> imageFiles = myImages(userId);
        List<String> urls = imageFiles.stream().map(ImageFile::getOssUrl).toList();
        if (!urls.contains(editImageRequest.getImage())) {
            throw new RuntimeException("只能编辑自己上传的图片");
        }
        EditImageResponse editImageResponse = pythonImageService.edit(editImageRequest);
        recordService.editSave(userId, editImageRequest, editImageResponse);
        return editImageResponse;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteImage(Long userId, Long imageId) {
        ImageFile record = imageFileMapper.selectById(imageId);
        if (record == null) {
            throw new RuntimeException("图片不存在");
        }
        if (!record.getUserId().equals(userId)) {
            throw new RuntimeException("只能删除自己的图片");
        }

        String ossUrl = record.getOssUrl();
        if (ossUrl != null && !ossUrl.isBlank()) {
            pythonImageService.deleteByUrl(ossUrl);
        }

        imageFileMapper.deleteById(imageId);

        try {
            Path localPath = Paths.get(uploadBaseDir, "images",
                    ossUrl != null ? ossUrl.substring(ossUrl.lastIndexOf('/') + 1) : "");
            Files.deleteIfExists(localPath);
        } catch (Exception ignored) {
        }
    }

    @Override
    public MergeImageResponse merge(Long userId, MergeImageRequest mergeImageRequest) {
        List<ImageFile> imageFiles = myImages(userId);
        List<String> urls = imageFiles.stream().map(ImageFile::getOssUrl).toList();
        if (!urls.contains(mergeImageRequest.getImage1()) || !urls.contains(mergeImageRequest.getImage2())) {
            throw new RuntimeException("只能合并自己上传的图片");
        }
        MergeImageResponse mergeImageResponse = pythonImageService.merge(mergeImageRequest);
        recordService.mergeSave(userId, mergeImageRequest, mergeImageResponse);
        return mergeImageResponse;
    }

    private String getFileExtension(String originalFileName, String contentType) {
        if (originalFileName != null && originalFileName.contains(".")) {
            String ext = originalFileName.substring(originalFileName.lastIndexOf(".")).toLowerCase(Locale.ROOT);
            if (ext.length() <= 10) {
                return ext;
            }
        }
        if (contentType == null) {
            return ".png";
        }
        if (contentType.equalsIgnoreCase("image/png")) {
            return ".png";
        }
        if (contentType.equalsIgnoreCase("image/jpeg") || contentType.equalsIgnoreCase("image/jpg")) {
            return ".jpg";
        }
        if (contentType.equalsIgnoreCase("image/gif")) {
            return ".gif";
        }
        if (contentType.equalsIgnoreCase("image/webp")) {
            return ".webp";
        }
        return ".png";
    }
}
