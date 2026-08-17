import com.intellij.codeInsight.template.postfix.templates.PostfixLiveTemplate;
import com.intellij.codeInsight.template.postfix.templates.PostfixTemplate;
import com.intellij.lang.ASTNode;
import com.intellij.lang.FileASTNode;
import com.intellij.lang.Language;
import com.intellij.lang.impl.PsiBuilderImpl;
import com.intellij.lexer.Lexer;
import com.intellij.lexer.MergingLexerAdapter;
import com.intellij.openapi.Disposable;
import com.intellij.openapi.application.Application;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.components.ComponentManager;
import com.intellij.openapi.editor.impl.DocumentImpl;
import com.intellij.openapi.extensions.ExtensionPoint;
import com.intellij.openapi.extensions.Extensions;
import com.intellij.codeInsight.multiverse.CodeInsightContext;
import com.intellij.openapi.fileTypes.FileType;
import com.intellij.openapi.extensions.impl.ExtensionsAreaImpl;
import com.intellij.openapi.progress.ProgressIndicator;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.openapi.vfs.VirtualFileFilter;
import com.intellij.psi.AbstractFileViewProvider;
import com.intellij.psi.FileViewProvider;
import com.intellij.psi.PsiDirectory;
import com.intellij.psi.PsiElement;
import com.intellij.psi.PsiFile;
import com.intellij.psi.PsiManager;
import com.intellij.psi.PsiReference;
import com.intellij.psi.PsiTreeChangeListener;
import com.intellij.psi.impl.PsiManagerEx;
import com.intellij.psi.impl.PsiTreeChangeEventImpl;
import com.intellij.psi.impl.PsiTreeChangePreprocessor;
import com.intellij.psi.impl.file.impl.FileManager;
import com.intellij.psi.impl.file.impl.FileManagerEx;
import com.intellij.psi.impl.source.CharTableImpl;
import com.intellij.psi.impl.source.tree.FileElement;
import com.intellij.psi.tree.TokenSet;
import com.intellij.psi.util.PsiModificationTracker;
import com.intellij.testFramework.LightVirtualFile;
import com.intellij.util.CharTable;
import com.jetbrains.python.PyElementTypesFacade;
import com.jetbrains.python.PyElementTypesFacadeImpl;
import com.jetbrains.python.PyTokenTypes;
import com.jetbrains.python.PythonDialectsTokenSetContributor;
import com.jetbrains.python.PythonDialectsTokenSetProvider;
import com.jetbrains.python.codeInsight.postfix.PyPostfixUtils;
import com.jetbrains.python.lexer.PythonIndentingLexer;
import com.jetbrains.python.parsing.SageParser;
import com.starnotesxj.sageide.parser.SageCaretLexer;
import com.starnotesxj.sageide.parser.SageParserDefinition;
import com.starnotesxj.sageide.sugar.SageFile;
import com.starnotesxj.sageide.sugar.SageFileElementType;
import com.starnotesxj.sageide.sugar.SageFileType;
import com.starnotesxj.sageide.sugar.SageLanguage;
import com.starnotesxj.sageide.sugar.SagePostfixTemplateProvider;
import kotlin.jvm.functions.Function0;

import java.lang.reflect.Proxy;
import java.util.List;

/**
 * Reproduces the postfix-completion applicability decision locally:
 * key computation + copy-file parse + template.isApplicable, for `m.ZZ`
 * in a Sage file, using the REAL plugin classes.
 */
public class TestPostfix {

  public static void main(String[] args) throws Exception {
    ComponentManager fakeManager = (ComponentManager)Proxy.newProxyInstance(
      ComponentManager.class.getClassLoader(),
      new Class<?>[]{ComponentManager.class},
      (proxy, method, a) -> {
        if (method.getName().equals("loadClass") && a.length >= 1) {
          try {
            return Class.forName((String)a[0]);
          }
          catch (ClassNotFoundException e) {
            return null;
          }
        }
        return defaultFor(method, proxy, a);
      });
    ExtensionsAreaImpl area = new ExtensionsAreaImpl(fakeManager);
    Extensions.setRootArea(area);
    Disposable fakeDisposable = (Disposable)Proxy.newProxyInstance(
      Disposable.class.getClassLoader(), new Class<?>[]{Disposable.class}, (proxy, method, a) -> null);
    area.registerExtensionPoint(
      PythonDialectsTokenSetContributor.EP_NAME,
      PythonDialectsTokenSetContributor.EP_NAME.getName(),
      ExtensionPoint.Kind.INTERFACE,
      fakeDisposable);
    area.registerExtensionPoint("com.intellij.lang.ast.factory", "com.intellij.lang.ast.factory",
                                ExtensionPoint.Kind.INTERFACE, false);
    // The Sage parser definition must be visible through the language EP —
    // PsiFileBase's ctor requires language.getParserDefinition() != null.
    area.registerExtensionPoint(
      com.intellij.lang.LanguageParserDefinitions.INSTANCE.getName(),
      com.intellij.lang.LanguageExtensionPoint.class.getName(),
      ExtensionPoint.Kind.INTERFACE,
      false);
    com.intellij.lang.LanguageExtensionPoint<com.intellij.lang.ParserDefinition> sagePd =
      new com.intellij.lang.LanguageExtensionPoint<>(
        SageLanguage.INSTANCE.getID(), new SageParserDefinition());
    sagePd.setPluginDescriptor(new com.intellij.openapi.extensions.DefaultPluginDescriptor(
      com.intellij.openapi.extensions.PluginId.getId("fake")));
    area.getExtensionPoint(com.intellij.lang.LanguageParserDefinitions.INSTANCE.getName())
        .registerExtension(sagePd, fakeDisposable);
    // Real Py PSI wrappers for the inner nodes (PyExpression etc.) — the
    // selector collects PyExpression parents, plain AST wrappers would not qualify.
    com.intellij.lang.LanguageExtensionPoint<com.intellij.lang.ParserDefinition> pyPd =
      new com.intellij.lang.LanguageExtensionPoint<>(
        "Python", new com.jetbrains.python.PythonParserDefinition());
    pyPd.setPluginDescriptor(new com.intellij.openapi.extensions.DefaultPluginDescriptor(
      com.intellij.openapi.extensions.PluginId.getId("fake")));
    area.getExtensionPoint(com.intellij.lang.LanguageParserDefinitions.INSTANCE.getName())
        .registerExtension(pyPd, fakeDisposable);
    final PythonDialectsTokenSetProvider provider2 = new PythonDialectsTokenSetProvider();

    final com.intellij.util.messages.MessageBus fakeBus =
      (com.intellij.util.messages.MessageBus)Proxy.newProxyInstance(
        com.intellij.util.messages.MessageBus.class.getClassLoader(),
        new Class<?>[]{com.intellij.util.messages.MessageBus.class},
        (proxy, method, a) -> {
          if (method.getName().equals("connect")) {
            return Proxy.newProxyInstance(
              com.intellij.util.messages.MessageBusConnection.class.getClassLoader(),
              new Class<?>[]{com.intellij.util.messages.MessageBusConnection.class},
              (p, m, msgArgs) -> defaultFor(m, p, msgArgs));
          }
          return defaultFor(method, proxy, a);
        });

    Application fakeApp = (Application)Proxy.newProxyInstance(
      Application.class.getClassLoader(),
      new Class<?>[]{Application.class},
      (proxy, method, a) -> {
        if (method.getName().equals("getService") && a.length == 1 &&
            a[0] == PythonDialectsTokenSetProvider.class) return provider2;
        if (method.getName().equals("getService") && a.length == 1 &&
            a[0] == PyElementTypesFacade.class) return new PyElementTypesFacadeImpl();
        if (method.getName().equals("getMessageBus")) return fakeBus;
        if (method.getName().equals("getExtensionArea")) return area;
        return defaultFor(method, proxy, a);
      });
    ApplicationManager.setApplication(fakeApp);

    Object fakeProject = Proxy.newProxyInstance(
      com.intellij.openapi.project.Project.class.getClassLoader(),
      new Class<?>[]{com.intellij.openapi.project.Project.class},
      (proxy, method, a) -> defaultFor(method, proxy, a));

    String text = "m = 1\nn = 1\nm.ZZ\nprint(m)\n";
    int caret = text.indexOf(".ZZ") + 3; // right after "ZZ"

    SagePostfixTemplateProvider sageProvider = new SagePostfixTemplateProvider();

    // 1. Key computation (the same walk PostfixLiveTemplate uses).
    String key = PostfixLiveTemplate.computeTemplateKeyWithoutContextChecking(sageProvider, text, caret);
    System.out.println("key for m.ZZ = '" + key + "'");

    // 2. Copy file (text minus the key) parsed with the real chain.
    int newOffset = caret - key.length();
    String copyText = text.substring(0, newOffset) + text.substring(caret);
    ASTNode root = parse(copyText);
    System.out.println("copy text: " + copyText.replace("\n", "\\n"));

    // 3. Context element at positiveOffset(newOffset) — replicate
    //    CustomTemplateCallback.getContext semantics (element at offset).
    int contextOffset = Math.max(0, newOffset - 1);
    ASTNode contextNode = findDeepest(root, contextOffset);
    PsiElement context = contextNode == null ? null : contextNode.getPsi();
    System.out.println("context at " + contextOffset + " = " +
                       (context == null ? "null" : context + " [" + context.getTextRange() + "]"));

    // 4. Applicability of every Sage template.
    DocumentImpl copyDocument = new DocumentImpl(copyText);
    System.out.println("--- template.isApplicable(context, copyDoc, newOffset=" + newOffset + ") ---");
    int applicable = 0;
    for (PostfixTemplate t : sageProvider.getTemplates()) {
      boolean app;
      try {
        app = t.isApplicable(context, copyDocument, newOffset);
      }
      catch (Throwable th) {
        System.out.println("  " + t.getKey() + "  THREW " + th);
        continue;
      }
      if (app) applicable++;
      System.out.println("  " + t.getKey() + " -> " + app);
    }
    System.out.println("applicable: " + applicable + "/" + sageProvider.getTemplates().size());

    // 5. The selector's view for the .ZZ key.
    List<PsiElement> exprs =
      PyPostfixUtils.selectorAllExpressionsWithCurrentOffset().getExpressions(context, copyDocument, newOffset);
    System.out.println("selector expressions: " + exprs.size() + (exprs.isEmpty() ? "" : " first=" + exprs.get(0).getText()));
  }

  static ASTNode parse(String text) {
    Lexer lexer = new SageCaretLexer(new Function0<Lexer>() {
      @Override
      public Lexer invoke() {
        return new MergingLexerAdapter(new PythonIndentingLexer(), TokenSet.create(PyTokenTypes.XOR));
      }
    });
    // FileElement (not plain LazyParseableElement): SharedImplUtil.getContainingFile
    // only resolves the PSI file when the topmost node implements FileASTNode.
    FileElement root = new FileElement(SageFileElementType.INSTANCE, text);
    root.putUserData(CharTable.CHAR_TABLE_KEY, new CharTableImpl());
    // Bind the SageFile PSI BEFORE PsiBuilderImpl runs — its ctor resolves
    // the containing file, and an unbound FileElement would fabricate a
    // non-file wrapper through createPsiNoLock.
    attachSageFilePsi(root);
    Object fakeProject = Proxy.newProxyInstance(
      com.intellij.openapi.project.Project.class.getClassLoader(),
      new Class<?>[]{com.intellij.openapi.project.Project.class},
      (proxy, method, a) -> defaultFor(method, proxy, a));
    PsiBuilderImpl builder = new PsiBuilderImpl(
      (com.intellij.openapi.project.Project)fakeProject, new SageParserDefinition(), lexer, root, text);
    ASTNode parsed = new SageParser().parse(SageFileElementType.INSTANCE, builder);
    if (parsed != root) {
      System.out.println("NOTE: parser returned a different root (" + parsed.getClass().getSimpleName() +
                         ") than the FileElement the PSI was bound to — re-binding");
      if (parsed instanceof FileElement) {
        attachSageFilePsi((FileElement)parsed);
      }
      else {
        throw new IllegalStateException("unexpected parse root type: " + parsed.getClass());
      }
    }
    return parsed;
  }

  /**
   * Binds a real SageFile PSI to the parse root so `context.containingFile`
   * (used by the isApplicable SageFile gate) resolves in the fake platform.
   */
  static void attachSageFilePsi(FileElement root) {
    final Object fakeProject = Proxy.newProxyInstance(
      com.intellij.openapi.project.Project.class.getClassLoader(),
      new Class<?>[]{com.intellij.openapi.project.Project.class},
      (proxy, method, a) -> defaultFor(method, proxy, a));
    final LightVirtualFile fakeVFile = new LightVirtualFile("test.sage", SageFileType.INSTANCE, root.getText());
    final PsiManager fakeManager = fakePsiManager(fakeProject);
    FileViewProvider fvp = new AbstractFileViewProvider(fakeManager, fakeVFile, false) {
      @Override public Language getBaseLanguage() { return SageLanguage.INSTANCE; }
      @Override public java.util.Set<Language> getLanguages() { return java.util.Collections.singleton(SageLanguage.INSTANCE); }
      @Override protected PsiFile getPsiInner(Language target) { return (PsiFile)root.getPsi(); }
      @Override public PsiFile getCachedPsi(Language target) { return (PsiFile)root.getPsi(); }
      @Override public java.util.List<PsiFile> getCachedPsiFiles() {
        return java.util.Collections.singletonList((PsiFile)root.getPsi());
      }
      @Override public java.util.List<FileASTNode> getKnownTreeRoots() {
        return java.util.Collections.singletonList(root);
      }
      @Override public PsiElement findElementAt(int offset, Class<? extends Language> lang) {
        ASTNode leaf = root.findLeafElementAt(offset);
        return leaf == null ? null : leaf.getPsi();
      }
      @Override public PsiElement findElementAt(int offset) {
        ASTNode leaf = root.findLeafElementAt(offset);
        return leaf == null ? null : leaf.getPsi();
      }
      @Override public PsiElement findElementAt(int offset, Language language) {
        ASTNode leaf = root.findLeafElementAt(offset);
        return leaf == null ? null : leaf.getPsi();
      }
      @Override public PsiReference findReferenceAt(int offset) { return null; }
      @Override public PsiReference findReferenceAt(int offset, Language language) { return null; }
      @Override public CharSequence getContents() { return root.getText(); }
      @Override public FileViewProvider createCopy(VirtualFile copy) { return this; }
      @Override public java.util.List<PsiFile> getAllFiles() {
        return java.util.Collections.singletonList((PsiFile)root.getPsi());
      }
      @Override public PsiFile getStubBindingRoot() { return (PsiFile)root.getPsi(); }
      @Override public String toString() { return "fake fvp for " + fakeVFile.getName(); }
    };
    root.setPsi(new SageFile(fvp));
  }

  /** Minimal PsiManagerEx stub for the fake platform (PsiFileImpl casts its manager to PsiManagerEx). */
  static PsiManager fakePsiManager(final Object fakeProject) {
    return new PsiManagerEx() {
      @Override public com.intellij.openapi.project.Project getProject() {
        return (com.intellij.openapi.project.Project)fakeProject;
      }
      @Override public PsiFile findFile(VirtualFile file) { return null; }
      @Override public PsiFile findFile(VirtualFile file, CodeInsightContext context) { return null; }
      @Override public FileViewProvider findViewProvider(VirtualFile file) { return null; }
      @Override public FileViewProvider findViewProvider(VirtualFile file, CodeInsightContext context) { return null; }
      @Override public PsiDirectory findDirectory(VirtualFile file) { return null; }
      @Override public boolean areElementsEquivalent(PsiElement element1, PsiElement element2) { return element1 == element2; }
      @Override public void reloadFromDisk(PsiFile psiFile) { }
      @Override public void addPsiTreeChangeListener(PsiTreeChangeListener listener) { }
      @Override public void addPsiTreeChangeListener(PsiTreeChangeListener listener, Disposable parentDisposable) { }
      @Override public void addPsiTreeChangeListenerBackgroundable(PsiTreeChangeListener listener, Disposable parentDisposable) { }
      @Override public void removePsiTreeChangeListener(PsiTreeChangeListener listener) { }
      @Override public PsiModificationTracker getModificationTracker() { return null; }
      @Override public void startBatchFilesProcessingMode() { }
      @Override public void finishBatchFilesProcessingMode() { }
      @Override public <T> T runInBatchFilesMode(com.intellij.openapi.util.Computable<T> runnable) { return runnable.compute(); }
      @Override public boolean isDisposed() { return false; }
      @Override public void dropResolveCaches() { }
      @Override public void dropPsiCaches() { }
      @Override public boolean isInProject(PsiElement element) { return true; }
      @Override public FileViewProvider findCachedViewProvider(VirtualFile vFile) { return null; }
      @Override public void cleanupForNextTest() { }
      @Override public void dropResolveCacheRegularly(ProgressIndicator indicator) { }
      @Override public boolean isBatchFilesProcessingMode() { return false; }
      @Override public void setAssertOnFileLoadingFilter(VirtualFileFilter filter, Disposable parentDisposable) { }
      @Override public boolean isAssertOnFileLoading(VirtualFile file) { return false; }
      @Override public FileManager getFileManager() { return null; }
      @Override public FileManagerEx getFileManagerEx() { return null; }
      @Override public void beforeChildAddition(PsiTreeChangeEventImpl event) { }
      @Override public void beforeChildRemoval(PsiTreeChangeEventImpl event) { }
      @Override public void beforeChildReplacement(PsiTreeChangeEventImpl event) { }
      @Override public void beforeChildrenChange(PsiTreeChangeEventImpl event) { }
      @Override public void beforeChildMovement(PsiTreeChangeEventImpl event) { }
      @Override public void beforePropertyChange(PsiTreeChangeEventImpl event) { }
      @Override public void childAdded(PsiTreeChangeEventImpl event) { }
      @Override public void childRemoved(PsiTreeChangeEventImpl event) { }
      @Override public void childReplaced(PsiTreeChangeEventImpl event) { }
      @Override public void childMoved(PsiTreeChangeEventImpl event) { }
      @Override public void childrenChanged(PsiTreeChangeEventImpl event) { }
      @Override public void propertyChanged(PsiTreeChangeEventImpl event) { }
      @Override public void addTreeChangePreprocessor(PsiTreeChangePreprocessor preprocessor, Disposable parentDisposable) { }
      @Override public void addTreeChangePreprocessor(PsiTreeChangePreprocessor preprocessor) { }
      @Override public void removeTreeChangePreprocessor(PsiTreeChangePreprocessor preprocessor) { }
      @Override public void addTreeChangePreprocessorBackgroundable(PsiTreeChangePreprocessor preprocessor, Disposable parentDisposable) { }
      @Override public void beforeChange(boolean isPhysical) { }
      @Override public void afterChange(boolean isPhysical) { }
    };
  }

  static ASTNode findDeepest(ASTNode node, int offset) {
    if (node.getTextRange().getStartOffset() > offset || node.getTextRange().getEndOffset() <= offset) {
      return null;
    }
    ASTNode child = node.getFirstChildNode();
    while (child != null) {
      ASTNode hit = findDeepest(child, offset);
      if (hit != null) return hit;
      child = child.getTreeNext();
    }
    return node;
  }

  static Object defaultFor(java.lang.reflect.Method method, Object proxy, Object[] a) {
    if (method.getName().equals("toString")) return "Fake";
    if (method.getName().equals("hashCode")) return System.identityHashCode(proxy);
    if (method.getName().equals("equals")) return proxy == a[0];
    Class<?> rt = method.getReturnType();
    if (rt == boolean.class) return false;
    if (rt == int.class) return 0;
    if (rt == long.class) return 0L;
    if (rt == char.class) return '\0';
    return null;
  }
}
